import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update

from app.config import get_settings
from app.db import SessionLocal
from app.languages import normalize_language
from app.models import Document, HealthSummary, UserProfile
from app.schemas import ExtractedData
from app.services.ai import disclaimer_for_language, get_ai_provider
from app.services.ocr import get_ocr_provider
from app.services.storage import get_storage
from app.services.timeline import rebuild_document_events

logger = logging.getLogger(__name__)


async def process_document(document_id: str) -> None:
    async with SessionLocal() as session:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=settings.processing_lease_seconds)
        claim = await session.execute(
            update(Document)
            .where(
                Document.id == document_id,
                or_(
                    Document.status == "queued",
                    and_(Document.status == "processing", Document.updated_at < stale_before),
                ),
            )
            .values(status="processing", processing_error=None, updated_at=now)
        )
        if not claim.rowcount:
            return
        await session.commit()
        document = await session.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            return
        owner = await session.get(UserProfile, document.owner_id)
        profile_language = owner.preferred_language if owner else "en"
        summary_language = normalize_language(profile_language)
        try:
            content = await get_storage().get(document.storage_key)
            ocr = await get_ocr_provider().analyze(content, document.mime_type)
            # Azure can return only the requested page range. Keep the full count
            # determined from the uploaded PDF so omitted pages remain visible.
            document.page_count = document.page_count or ocr.page_count
            document.pages_processed = min(ocr.pages_processed, settings.max_document_pages)
            document.ocr_text = ocr.raw_text
            machine_baseline = None

            if not ocr.raw_text.strip():
                extracted = ExtractedData(
                    document_type="other",
                    notes={
                        "en": "No text was extracted. Verify the document and retry with OCR configured.",
                        "hi": "दस्तावेज़ से पाठ नहीं निकला। स्रोत दस्तावेज़ जाँचें और OCR कॉन्फ़िगरेशन सत्यापित करें।",
                        "ta": "ஆவணத்திலிருந்து உரை எடுக்கப்படவில்லை. மூல ஆவணத்தைச் சரிபார்த்து OCR அமைப்பை மீண்டும் முயற்சிக்கவும்.",
                        "te": "పత్రం నుండి వచనం సేకరించబడలేదు. మూల పత్రాన్ని తనిఖీ చేసి OCRని మళ్లీ ప్రయత్నించండి.",
                        "ml": "രേഖയിൽ നിന്ന് വാചകം ലഭിച്ചില്ല. ഉറവിട രേഖ പരിശോധിച്ച് OCR ക്രമീകരണം വീണ്ടും ശ്രമിക്കുക.",
                    }[summary_language],
                    overall_confidence=0,
                )
                summary_lead = {
                    "en": "No document text was extracted, so a health summary cannot be generated. Check document processing and verify the source document.",
                    "hi": "दस्तावेज़ से पाठ नहीं निकला, इसलिए स्वास्थ्य सारांश नहीं बनाया जा सकता। प्रोसेसिंग सेटिंग जाँचें और स्रोत दस्तावेज़ सत्यापित करें।",
                    "ta": "ஆவணத்திலிருந்து உரை எடுக்கப்படாததால் சுகாதாரச் சுருக்கத்தை உருவாக்க முடியவில்லை. செயலாக்க அமைப்பைச் சரிபார்த்து மூல ஆவணத்தைப் பார்க்கவும்.",
                    "te": "పత్రం నుండి వచనం సేకరించబడలేదు కాబట్టి ఆరోగ్య సారాంశం రూపొందించలేము. ప్రాసెసింగ్ సెట్టింగ్‌లను తనిఖీ చేసి మూల పత్రాన్ని పరిశీలించండి.",
                    "ml": "രേഖയിൽ നിന്ന് വാചകം ലഭിക്കാത്തതിനാൽ ആരോഗ്യ സംഗ്രഹം സൃഷ്ടിക്കാനായില്ല. പ്രോസസ്സിംഗ് ക്രമീകരണം പരിശോധിച്ച് ഉറവിട രേഖ ഉറപ്പാക്കുക.",
                }[summary_language]
                summary_text = f"{summary_lead}\n\n{disclaimer_for_language(summary_language)}"
                model_name = "none"
                document.status = "needs_review"
            else:
                ai = get_ai_provider()
                try:
                    extracted = await ai.extract(ocr.raw_text)
                    machine_baseline = extracted.model_dump(mode="json")
                    if document.page_count and document.pages_processed < document.page_count:
                        omitted = document.page_count - document.pages_processed
                        coverage_note = (
                            f"Only the first {document.pages_processed} of {document.page_count} pages "
                            f"were processed; {omitted} page(s) were not analyzed."
                        )
                        machine_baseline["notes"] = (
                            f"{machine_baseline['notes']}\n{coverage_note}"
                            if machine_baseline.get("notes")
                            else coverage_note
                        )
                    extracted = ExtractedData.model_validate(
                        {**machine_baseline, **(document.extraction_overrides or {})}
                    )
                    summary_text = await ai.summarize(extracted, summary_language)
                    model_name = settings.summary_deployment if settings.llm_provider == "azure" else "mock"
                    document.document_type = extracted.document_type
                    document.document_date = extracted.document_date
                finally:
                    if hasattr(ai, "close"):
                        await ai.close()
                document.status = (
                    "completed"
                    if settings.ocr_provider == "azure"
                    and settings.llm_provider == "azure"
                    and float((machine_baseline or {}).get("overall_confidence", 0)) >= 0.6
                    and document.pages_processed >= (document.page_count or 0)
                    else "needs_review"
                )

            baseline = machine_baseline or extracted.model_dump(mode="json")
            if ocr.raw_text.strip() or document.extraction_baseline is None:
                document.extraction_baseline = baseline
            else:
                baseline = document.extraction_baseline
            merged = {**baseline, **(document.extraction_overrides or {})}
            extracted = ExtractedData.model_validate(merged)
            document.extracted_data = merged
            document.document_type = extracted.document_type
            document.document_date = extracted.document_date
            document.processing_error = None
            await rebuild_document_events(session, document, extracted)
            session.add(
                HealthSummary(
                    owner_id=document.owner_id,
                    document_id=document.id,
                    language=summary_language,
                    summary_text=summary_text,
                    model_name=model_name or "azure-openai",
                    prompt_version="summary-v2",
                )
            )
            await session.commit()
        except Exception as exc:
            logger.error(
                "Document processing failed: error_type=%s",
                type(exc).__name__,
            )
            await session.rollback()
            failed_document = await session.scalar(select(Document).where(Document.id == document_id))
            if failed_document:
                failed_document.status = "failed"
                failed_document.processing_error = getattr(exc, "code", "PROCESSING_FAILED")
                await session.commit()
