from datetime import datetime, timezone
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentProfile
from app.db import get_session
from app.models import Document

router = APIRouter(prefix="/profile/me/fhir", tags=["fhir"])
Session = Annotated[AsyncSession, Depends(get_session)]
FHIR_XHTML = "http://www.w3.org/1999/xhtml"


def _entry(resource: dict) -> dict:
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


@router.get("")
async def get_fhir_bundle(profile: CurrentProfile, session: Session) -> dict:
    documents = await session.scalars(
        select(Document)
        .where(Document.owner_id == profile.id, Document.status.in_(["completed", "needs_review"]))
        .options(selectinload(Document.summaries))
        .order_by(Document.created_at)
    )
    gender = (profile.gender or "unknown").strip().lower()
    if gender not in {"male", "female", "other", "unknown"}:
        gender = "unknown"
    patient = {
        "resourceType": "Patient",
        "id": profile.id,
        "name": [{"text": profile.display_name}] if profile.display_name else [],
        "gender": gender,
    }
    if profile.birth_date:
        patient["birthDate"] = profile.birth_date.isoformat()
    entries = [_entry(patient)]
    device_id = f"carefolio-{profile.id}"
    entries.append(
        _entry(
            {
                "resourceType": "Device",
                "id": device_id,
                "status": "active",
                "deviceName": [{"name": "Carefolio AI Health Copilot", "type": "user-friendly-name"}],
            }
        )
    )

    for document in documents:
        data = document.extracted_data or {}
        observation_refs: list[dict] = []
        for index, result in enumerate(data.get("lab_results", [])):
            observation_id = f"{document.id}-observation-{index}"
            observation = {
                "resourceType": "Observation",
                "id": observation_id,
                "status": "unknown",
                "subject": {"reference": f"urn:uuid:{profile.id}"},
                "code": {"text": result.get("test_name") or "Unspecified test"},
            }
            event_date = result.get("date") or data.get("document_date")
            if event_date:
                observation["effectiveDateTime"] = event_date
            value_parts = [result.get("value"), result.get("unit")]
            value = " ".join(part for part in value_parts if part)
            if value:
                observation["valueString"] = value
            if result.get("reference_range"):
                observation["referenceRange"] = [{"text": f"As reported: {result['reference_range']}"}]
            if result.get("flag"):
                observation["interpretation"] = [{"text": f"Source document flag: {result['flag']}"}]
            entries.append(_entry(observation))
            observation_refs.append({"reference": f"urn:uuid:{observation_id}"})

        for index, medication in enumerate(data.get("medications", [])):
            medication_id = f"{document.id}-medication-{index}"
            request = {
                "resourceType": "MedicationRequest",
                "id": medication_id,
                "status": "unknown",
                "intent": "order",
                "subject": {"reference": f"urn:uuid:{profile.id}"},
                "medicationCodeableConcept": {"text": medication.get("name") or "Unspecified medication"},
            }
            dosage = ", ".join(
                filter(None, [medication.get("dosage"), medication.get("frequency"), medication.get("instructions")])
            )
            if dosage:
                request["dosageInstruction"] = [{"text": dosage}]
            event_date = data.get("document_date")
            if event_date:
                request["authoredOn"] = event_date
            entries.append(_entry(request))

        for index, diagnosis in enumerate(data.get("diagnoses", [])):
            condition_id = f"{document.id}-condition-{index}"
            condition = {
                "resourceType": "Condition",
                "id": condition_id,
                "subject": {"reference": f"urn:uuid:{profile.id}"},
                "code": {"text": diagnosis.get("name") or "Unspecified condition"},
            }
            condition_date = diagnosis.get("date") or data.get("document_date")
            if condition_date:
                condition["onsetDateTime"] = condition_date
            entries.append(_entry(condition))

        report_id = f"{document.id}-diagnostic-report"
        report = {
            "resourceType": "DiagnosticReport",
            "id": report_id,
            "status": "unknown",
            "code": {"text": (data.get("document_type") or "other").replace("_", " ").title()},
            "subject": {"reference": f"urn:uuid:{profile.id}"},
        }
        if data.get("document_date"):
            report["effectiveDateTime"] = data["document_date"]
        if observation_refs:
            report["result"] = observation_refs
        entries.append(_entry(report))

        summary = document.summaries[-1] if document.summaries else None
        if summary:
            composition_id = f"{document.id}-summary"
            safe_summary = escape(summary.summary_text)
            composition = {
                "resourceType": "Composition",
                "id": composition_id,
                "status": "final",
                "type": {"text": "AI-generated patient information summary"},
                "subject": {"reference": f"urn:uuid:{profile.id}"},
                "date": summary.created_at.isoformat(),
                "author": [{"reference": f"urn:uuid:{device_id}"}],
                "title": "AI-generated summary; not a clinical record",
                "section": [
                    {
                        "title": "Summary",
                        "text": {
                            "status": "generated",
                            "div": f'<div xmlns="{FHIR_XHTML}"><p>{safe_summary}</p></div>',
                        },
                    }
                ],
            }
            entries.append(_entry(composition))

    return {
        "resourceType": "Bundle",
        "id": f"health-{profile.id}",
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entries,
    }
