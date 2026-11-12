"""Knowledge API schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OfficeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    opening_hours: str = ""


class OfficeUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    opening_hours: str | None = None


class OfficeOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    contact_person: str
    phone: str
    email: str
    opening_hours: str
    created_at: datetime


class EntryCreate(BaseModel):
    office_id: UUID
    category: str = ""
    subcategory: str = ""
    verbatim_only: bool = False
    escalate_to_human: bool = False
    applicability: dict[str, Any] = Field(default_factory=dict)
    season: str | None = None
    answer_text: str = Field(min_length=1)
    source_document: str | None = None
    last_verified: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    question_raw: str | None = None
    language: str = "en"
    asker_type: str | None = None
    channel: str | None = None


class VersionCreate(BaseModel):
    answer_text: str = Field(min_length=1)
    source_document: str | None = None
    last_verified: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None


class VersionOut(BaseModel):
    id: UUID
    entry_id: UUID
    version_number: int
    answer_text: str
    source_document: str | None
    last_verified: date | None
    valid_from: date | None
    valid_until: date | None
    status: str
    editor_id: UUID
    approver_id: UUID | None
    approved_at: datetime | None
    published_at: datetime | None
    created_at: datetime


class EntryOut(BaseModel):
    id: UUID
    tenant_id: UUID
    office_id: UUID
    category: str
    subcategory: str
    verbatim_only: bool
    escalate_to_human: bool
    applicability: dict[str, Any]
    season: str | None
    created_at: datetime
    latest_version: VersionOut | None = None


class NeedsAnswerOut(BaseModel):
    id: UUID
    question_raw: str
    category: str | None
    subcategory: str | None
    language: str | None
    office_id: UUID | None
    status: str
    created_at: datetime


class ImportPreviewOut(BaseModel):
    headers: list[str]
    suggested_mapping: dict[str, str]
    sample_rows: list[dict[str, Any]]
    row_count: int


class ImportRunRequest(BaseModel):
    mapping: dict[str, str]
    default_office_id: UUID | None = None


class ImportRunOut(BaseModel):
    job_id: UUID
    created_entries: int
    needs_answer: int
    skipped: int


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1)
    adapter_type: str = Field(pattern="^(spreadsheet|rest_json)$")
    config: dict[str, Any] = Field(default_factory=dict)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    schedule_cron: str | None = None


class ConnectorOut(BaseModel):
    id: UUID
    name: str
    adapter_type: str
    field_mapping: dict[str, Any]
    schedule_cron: str | None
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime


class SyncOut(BaseModel):
    job_id: UUID
    drafts_created: int
    needs_answer: int


class MessageOut(BaseModel):
    message: str
