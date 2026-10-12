from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

DocumentType = Literal["prescription", "lab_report", "discharge_summary", "diagnostic", "other"]
LabFlag = Literal["H", "L", "N", "HH", "LL"]
DocumentStatus = Literal["queued", "processing", "completed", "needs_review", "failed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class Medication(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    dosage: str | None = Field(default=None, max_length=160)
    frequency: str | None = Field(default=None, max_length=160)
    duration: str | None = Field(default=None, max_length=160)
    route: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)


class LabResult(StrictModel):
    test_name: str = Field(min_length=1, max_length=255)
    value: str | None = Field(default=None, max_length=160)
    unit: str | None = Field(default=None, max_length=100)
    reference_range: str | None = Field(default=None, max_length=160)
    flag: LabFlag | None = None
    date: Date | None = None
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)


class Diagnosis(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    date: Date | None = None
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)


class PatientInfo(StrictModel):
    name: str | None = Field(default=None, max_length=160)
    age: str | None = Field(default=None, max_length=40)
    gender: str | None = Field(default=None, max_length=80)
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)


class ExtractedData(StrictModel):
    document_type: DocumentType = "other"
    patient_info: PatientInfo | None = None
    medications: list[Medication] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    document_date: Date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    overall_confidence: float = Field(default=0, ge=0, le=1)


class ProfileRead(StrictModel):
    id: str
    display_name: str | None
    preferred_language: str
    birth_date: Date | None
    gender: str | None
    created_at: datetime
    updated_at: datetime


class ProfilePatch(StrictModel):
    display_name: str | None = Field(default=None, max_length=160)
    preferred_language: str | None = Field(default=None, min_length=2, max_length=16)
    birth_date: Date | None = None
    gender: str | None = Field(default=None, max_length=80)


class SummaryRead(StrictModel):
    id: str
    document_id: str
    language: str
    summary_text: str
    prompt_version: str
    model_name: str
    is_user_edited: bool
    created_at: datetime
    updated_at: datetime


class SummaryPatch(StrictModel):
    summary_text: str = Field(min_length=1, max_length=20000)
    language: str | None = Field(default=None, min_length=2, max_length=16)


class SummaryGenerateRequest(StrictModel):
    language: str | None = Field(default=None, min_length=2, max_length=16)


class DocumentRead(StrictModel):
    id: str
    display_name: str
    mime_type: str
    size_bytes: int
    page_count: int | None
    pages_processed: int
    document_type: str | None
    document_date: Date | None
    status: DocumentStatus
    extracted_data: ExtractedData
    summaries: list[SummaryRead]
    processing_error: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def pages_omitted(self) -> int:
        if self.page_count is None:
            return 0
        return max(0, self.page_count - self.pages_processed)


class DocumentListItem(StrictModel):
    id: str
    display_name: str
    mime_type: str
    size_bytes: int
    document_type: str | None
    document_date: Date | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentPatch(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    document_type: DocumentType | None = None
    document_date: Date | None = None
    extracted_data: ExtractedData | None = None

    @field_validator("display_name")
    @classmethod
    def non_empty_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Display name cannot be blank")
        return value


class TimelineEventRead(StrictModel):
    id: str
    document_id: str | None
    event_type: str
    event_date: Date | None
    title: str
    description: str | None
    data: dict
    is_user_edited: bool
    created_at: datetime
    updated_at: datetime


class TimelineEventPatch(StrictModel):
    event_date: Date | None = None
    event_type: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    data: dict | None = None

    @field_validator("data")
    @classmethod
    def limit_data_size(cls, value: dict | None) -> dict | None:
        import json

        if value is not None and len(json.dumps(value, ensure_ascii=False)) > 100_000:
            raise ValueError("Timeline event data exceeds the 100 KB limit")
        return value


class PaginatedDocuments(StrictModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class PaginatedTimeline(StrictModel):
    items: list[TimelineEventRead]
    total: int
    limit: int
    offset: int


class UploadAccepted(StrictModel):
    document_id: str
    status: DocumentStatus


class BlobAccess(StrictModel):
    url: str | None
    expires_in_seconds: int | None
    download_endpoint: str | None


class ErrorResponse(StrictModel):
    detail: str
    code: str | None = None
