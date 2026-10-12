from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentProfile
from app.config import get_settings
from app.db import get_session
from app.languages import add_disclaimer, normalize_language
from app.models import AuditLog, Document, HealthSummary, TimelineEvent
from app.schemas import (
    BlobAccess,
    DocumentListItem,
    DocumentPatch,
    DocumentRead,
    PaginatedDocuments,
    SummaryPatch,
    SummaryGenerateRequest,
    SummaryRead,
    UploadAccepted,
    ExtractedData,
)
from app.services.ai import get_ai_provider
from app.services.pipeline import process_document
from app.services.queue import get_document_queue
from app.services.storage import get_storage
from app.services.timeline import rebuild_document_events

router = APIRouter(prefix="/documents", tags=["documents"])
Session = Annotated[AsyncSession, Depends(get_session)]
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
EXTENSION_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


async def enqueue_document_processing(background_tasks: BackgroundTasks, document_id: str) -> None:
    settings = get_settings()
    if settings.queue_provider == "azure":
        await get_document_queue().enqueue(document_id)
    else:
        background_tasks.add_task(process_document, document_id)


def detect_type(filename: str, content: bytes, declared_type: str | None) -> str:
    extension_type = EXTENSION_TYPES.get(Path(filename).suffix.lower())
    if extension_type is None or extension_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF, JPG, and PNG files are supported")
    detected = None
    if content.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    if detected != extension_type or (declared_type and declared_type not in {detected, "application/octet-stream"}):
        raise HTTPException(status_code=415, detail="File content does not match its file type")
    return detected


def count_pdf_pages(content: bytes, mime_type: str) -> int | None:
    if mime_type != "application/pdf":
        return 1
    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise HTTPException(status_code=422, detail="Encrypted PDF files are not supported")
        return len(reader.pages)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read PDF page information") from exc


def record_audit(
    session: AsyncSession,
    actor_profile_id: str,
    document_id: str | None,
    action: str,
    details: dict,
) -> None:
    session.add(
        AuditLog(
            actor_profile_id=actor_profile_id,
            document_id=document_id,
            action=action,
            details=details,
        )
    )


@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    profile: CurrentProfile,
    session: Session,
    file: Annotated[UploadFile, File()],
) -> UploadAccepted:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB limit")
    filename = Path((file.filename or "health-document").replace("\\", "/")).name
    mime_type = detect_type(filename, content, file.content_type)
    pages = count_pdf_pages(content, mime_type)
    if pages == 0:
        raise HTTPException(status_code=422, detail="The PDF contains no pages")
    document_id = str(uuid4())
    storage_key = f"{profile.id}/{document_id}/{uuid4().hex}{Path(filename).suffix.lower()}"
    try:
        await get_storage().put(storage_key, content, mime_type)
        document = Document(
            id=document_id,
            owner_id=profile.id,
            display_name=filename[:255],
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=len(content),
            page_count=pages,
            pages_processed=0,
            status="queued",
            extracted_data={
                "document_type": "other",
                "patient_info": None,
                "medications": [],
                "lab_results": [],
                "diagnoses": [],
                "document_date": None,
                "notes": None,
                "overall_confidence": 0,
            },
        )
        session.add(document)
        record_audit(
            session,
            profile.id,
            document_id,
            "document.uploaded",
            {"mime_type": mime_type, "size_bytes": len(content), "page_count": pages},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await get_storage().delete(storage_key)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Document could not be saved") from None
    try:
        await enqueue_document_processing(background_tasks, document_id)
    except Exception as exc:
        document.status = "failed"
        document.processing_error = "QUEUE_ENQUEUE_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=503,
            detail="The document was saved, but processing could not be queued. Retry processing from the document record.",
        ) from exc
    return UploadAccepted(
        document_id=document_id,
        status="queued" if settings.queue_provider == "azure" else "processing",
    )


@router.get("", response_model=PaginatedDocuments)
async def list_documents(
    profile: CurrentProfile,
    session: Session,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedDocuments:
    base = select(Document).where(Document.owner_id == profile.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = await session.scalars(
        base.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    )
    return PaginatedDocuments(items=list(items), total=total, limit=limit, offset=offset)


async def get_owned_document(session: AsyncSession, owner_id: str, document_id: str) -> Document:
    document = await session.scalar(
        select(Document)
        .where(Document.id == document_id, Document.owner_id == owner_id)
        .options(selectinload(Document.summaries))
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: str, profile: CurrentProfile, session: Session) -> Document:
    return await get_owned_document(session, profile.id, document_id)


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: str, payload: DocumentPatch, profile: CurrentProfile, session: Session
) -> Document:
    document = await get_owned_document(session, profile.id, document_id)
    changes = payload.model_dump(exclude_unset=True)
    if "display_name" in changes and changes["display_name"] is None:
        raise HTTPException(status_code=422, detail="Display name cannot be null")
    if "document_type" in changes and changes["document_type"] is None:
        raise HTTPException(status_code=422, detail="Document type cannot be null")
    changed_fields = [
        field
        for field in ("display_name", "document_type", "document_date")
        if field in changes and changes[field] != getattr(document, field)
    ]
    if (
        "extracted_data" in changes
        and payload.extracted_data.model_dump(mode="json") != document.extracted_data
    ):
        changed_fields.append("extracted_data")
    for field in ("display_name", "document_type", "document_date"):
        if field in changes:
            setattr(document, field, changes[field])
    if "extracted_data" in changes:
        extracted = payload.extracted_data
        if extracted is None:
            raise HTTPException(status_code=422, detail="Extracted data cannot be null")
        document.extracted_data = extracted.model_dump(mode="json")
        document.document_type = extracted.document_type
        document.document_date = extracted.document_date
        baseline = document.extraction_baseline or {}
        manual_data = extracted.model_dump(mode="json")
        overrides = dict(document.extraction_overrides or {})
        for field, value in manual_data.items():
            if value == baseline.get(field):
                overrides.pop(field, None)
            else:
                overrides[field] = value
        document.extraction_overrides = overrides
        await rebuild_document_events(session, document, extracted)
    else:
        extracted = None
        extracted_payload = dict(document.extracted_data or {})
        if "document_type" in changes:
            extracted_payload["document_type"] = changes["document_type"]
        if "document_date" in changes:
            extracted_payload["document_date"] = (
                changes["document_date"].isoformat() if changes["document_date"] else None
            )
        if "document_type" in changes or "document_date" in changes:
            document.extracted_data = extracted_payload
            baseline = document.extraction_baseline or {}
            overrides = dict(document.extraction_overrides or {})
            for field in ("document_type", "document_date"):
                if field not in changes:
                    continue
                value = extracted_payload.get(field)
                if value == baseline.get(field):
                    overrides.pop(field, None)
                else:
                    overrides[field] = value
            document.extraction_overrides = overrides
            await rebuild_document_events(session, document, ExtractedData.model_validate(extracted_payload))
    if "display_name" in changes and extracted is None:
        event = await session.scalar(
            select(TimelineEvent).where(
                TimelineEvent.document_id == document.id,
                TimelineEvent.event_type == "document",
            )
        )
        if event:
            event.title = document.display_name
            event.is_user_edited = True
    if changed_fields:
        record_audit(session, profile.id, document.id, "document.edited", {"changed_fields": changed_fields})
    await session.commit()
    return await get_owned_document(session, profile.id, document_id)


@router.delete("/{document_id}/extraction-overrides", response_model=DocumentRead)
async def reset_extraction_overrides(
    document_id: str, profile: CurrentProfile, session: Session
) -> Document:
    document = await get_owned_document(session, profile.id, document_id)
    if document.extraction_baseline is None:
        raise HTTPException(status_code=409, detail="No processed extraction is available to restore")
    document.extraction_overrides = {}
    document.extracted_data = document.extraction_baseline
    extracted = ExtractedData.model_validate(document.extraction_baseline)
    document.document_type = extracted.document_type
    document.document_date = extracted.document_date
    await rebuild_document_events(session, document, extracted)
    record_audit(session, profile.id, document.id, "document.edited", {"changed_fields": ["extracted_data"]})
    await session.commit()
    return await get_owned_document(session, profile.id, document_id)


@router.post("/{document_id}/reprocess", response_model=UploadAccepted, status_code=202)
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    profile: CurrentProfile,
    session: Session,
) -> UploadAccepted:
    document = await get_owned_document(session, profile.id, document_id)
    if document.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already processing")
    document.status = "queued"
    document.processing_error = None
    record_audit(session, profile.id, document.id, "document.reprocessed", {})
    await session.commit()
    try:
        await enqueue_document_processing(background_tasks, document.id)
    except Exception as exc:
        document.status = "failed"
        document.processing_error = "QUEUE_ENQUEUE_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=503,
            detail="Processing could not be queued. Retry the request after checking queue configuration.",
        ) from exc
    return UploadAccepted(
        document_id=document.id,
        status="queued" if get_settings().queue_provider == "azure" else "processing",
    )


@router.get("/{document_id}/content-url", response_model=BlobAccess)
async def get_content_url(document_id: str, profile: CurrentProfile, session: Session) -> BlobAccess:
    await get_owned_document(session, profile.id, document_id)
    # Browser content is streamed through this authenticated endpoint. Blob containers
    # remain private; no public URL or long-lived SAS is exposed.
    return BlobAccess(url=None, expires_in_seconds=None, download_endpoint=f"/api/documents/{document_id}/content")


@router.get("/{document_id}/content")
async def download_content(document_id: str, profile: CurrentProfile, session: Session) -> Response:
    document = await get_owned_document(session, profile.id, document_id)
    try:
        content = await get_storage().get(document.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored document is unavailable") from exc
    record_audit(
        session,
        profile.id,
        document.id,
        "document.downloaded",
        {"size_bytes": len(content), "mime_type": document.mime_type},
    )
    await session.commit()
    filename = quote(document.display_name, safe="")
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/{document_id}/summary/{summary_id}", response_model=SummaryRead)
async def update_summary(
    document_id: str,
    summary_id: str,
    payload: SummaryPatch,
    profile: CurrentProfile,
    session: Session,
) -> HealthSummary:
    await get_owned_document(session, profile.id, document_id)
    summary = await session.scalar(
        select(HealthSummary).where(
            HealthSummary.id == summary_id,
            HealthSummary.document_id == document_id,
            HealthSummary.owner_id == profile.id,
        )
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    if payload.language is not None:
        summary.language = payload.language
    summary.language = normalize_language(summary.language)
    summary.summary_text = add_disclaimer(payload.summary_text, summary.language)
    summary.is_user_edited = True
    record_audit(session, profile.id, document_id, "summary.edited", {"summary_id": summary.id})
    await session.commit()
    await session.refresh(summary)
    return summary


@router.post("/{document_id}/summaries", response_model=SummaryRead, status_code=201)
async def generate_summary(
    document_id: str,
    payload: SummaryGenerateRequest,
    profile: CurrentProfile,
    session: Session,
) -> HealthSummary:
    document = await get_owned_document(session, profile.id, document_id)
    extracted = ExtractedData.model_validate(document.extracted_data)
    if document.page_count and document.pages_processed < document.page_count:
        coverage_note = (
            f"Only the first {document.pages_processed} of {document.page_count} pages were processed; "
            f"{document.page_count - document.pages_processed} page(s) were not analyzed."
        )
        extracted.notes = f"{extracted.notes}\n{coverage_note}" if extracted.notes else coverage_note
    language = normalize_language(payload.language or profile.preferred_language)
    ai = get_ai_provider()
    try:
        summary_text = await ai.summarize(extracted, language)
    finally:
        if hasattr(ai, "close"):
            await ai.close()
    summary = HealthSummary(
        owner_id=profile.id,
        document_id=document.id,
        language=language,
        summary_text=summary_text,
        model_name=(
            get_settings().summary_deployment
            if get_settings().llm_provider == "azure"
            else "mock"
        ) or "mock",
        prompt_version="summary-v2",
    )
    session.add(summary)
    await session.commit()
    await session.refresh(summary)
    return summary


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, profile: CurrentProfile, session: Session) -> None:
    document = await get_owned_document(session, profile.id, document_id)
    storage_key = document.storage_key
    try:
        await get_storage().delete(storage_key)
    except FileNotFoundError:
        pass
    await session.execute(delete(TimelineEvent).where(TimelineEvent.document_id == document.id))
    record_audit(session, profile.id, document.id, "document.deleted", {})
    await session.delete(document)
    await session.commit()
