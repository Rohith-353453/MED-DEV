from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, TimelineEvent
from app.schemas import ExtractedData


async def rebuild_document_events(session: AsyncSession, document: Document, extracted: ExtractedData) -> None:
    await session.execute(
        delete(TimelineEvent).where(
            TimelineEvent.document_id == document.id, TimelineEvent.is_user_edited.is_(False)
        )
    )
    existing_document_event = await session.scalar(
        select(TimelineEvent).where(
            TimelineEvent.document_id == document.id,
            TimelineEvent.event_type == "document",
            TimelineEvent.is_user_edited.is_(True),
        )
    )
    events = []
    if existing_document_event is None:
        events.append(TimelineEvent(
            owner_id=document.owner_id,
            document_id=document.id,
            event_type="document",
            event_date=extracted.document_date or document.document_date,
            title=document.display_name,
            description=f"{extracted.document_type.replace('_', ' ').title()} document",
            data={"document_type": extracted.document_type},
        ))
    for lab in extracted.lab_results:
        events.append(
            TimelineEvent(
                owner_id=document.owner_id,
                document_id=document.id,
                event_type="lab_result",
                event_date=lab.date or extracted.document_date or document.document_date,
                title=lab.test_name,
                description=f"{lab.value or 'Value not recorded'} {lab.unit or ''}".strip(),
                data=lab.model_dump(mode="json"),
            )
        )
    for medication in extracted.medications:
        events.append(
            TimelineEvent(
                owner_id=document.owner_id,
                document_id=document.id,
                event_type="medication",
                event_date=extracted.document_date or document.document_date,
                title=medication.name,
                description="Medication listed in document",
                data=medication.model_dump(mode="json"),
            )
        )
    for diagnosis in extracted.diagnoses:
        events.append(
            TimelineEvent(
                owner_id=document.owner_id,
                document_id=document.id,
                event_type="diagnosis",
                event_date=diagnosis.date or extracted.document_date or document.document_date,
                title=diagnosis.name,
                description="Condition listed in document",
                data=diagnosis.model_dump(mode="json"),
            )
        )
    session.add_all(events)
