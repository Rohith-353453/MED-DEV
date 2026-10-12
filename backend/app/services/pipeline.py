import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update

from app.config import get_settings
from app.db import SessionLocal
from app.models import Document, HealthSummary
from app.schemas import ExtractedData
from app.services.ai import DISCLAIMER, get_ai_provider
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
                    notes="No text was extracted. Verify the document and retry with OCR configured.",
                    overall_confidence=0,
                )
                summary_text = (
                    "No document text was extracted, so a health summary cannot be generated. "
                    "Check that document processing is configured and verify the source document.\n\n"
                    + DISCLAIMER
                )
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
                    summary_text = await ai.summarize(extracted)
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
                    language="en",
                    summary_text=summary_text,
                    model_name=model_name or "azure-openai",
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
