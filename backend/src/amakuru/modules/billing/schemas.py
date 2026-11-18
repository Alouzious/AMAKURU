"""Billing / onboarding / API key schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class PlanOut(BaseModel):
    code: str
    name: str
    description: str
    entitlements: dict[str, Any]


class UsageRowOut(BaseModel):
    day: date
    event_type: str
    quantity: int
    estimated_cost_usd: Decimal


class BillingSummaryOut(BaseModel):
    plan: str
    plan_detail: PlanOut
    entitlements: dict[str, Any]
    usage: dict[str, int]
    residency_mode: str
    branding: dict[str, Any]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["ask"])


class ApiKeyOut(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    raw_key: str
    message: str = "Store this key now; it will not be shown again."


class BrandingPatch(BaseModel):
    accent: str | None = None
    label: str | None = None
    display_name: str | None = None
    logo_url: str | None = None
    surface: str | None = None
    heading_font: str | None = None
    custom_domain: str | None = None


class OfficeSeedIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    opening_hours: str | None = None


class PastePairIn(BaseModel):
    """One Q&A pair the organization shared with you at create time."""

    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    office: str | None = Field(default=None, max_length=128)


class OnboardRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    plan: str = Field(default="starter")
    default_language: str = Field(default="en", max_length=8)
    residency_mode: str = Field(default="hosted")
    accent: str = Field(default="#0F4C5C")
    admin_email: EmailStr
    admin_full_name: str = Field(default="Tenant Administrator", max_length=255)
    admin_password: str = Field(min_length=12, max_length=128)
    offices: list[OfficeSeedIn] = Field(default_factory=list)
    seed_demo_answers: bool = False
    is_demo: bool = False
    # Where this org's answers come from (private; never put in the public widget snippet).
    # demo = Amakuru sample; none = empty bank; paste = Q&A they shared; sql/rest/website = connector.
    knowledge_source: str = Field(
        default="demo",
        pattern="^(demo|none|paste|sql_db|rest_json|website)$",
    )
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    site_origin: str | None = Field(default=None, max_length=512)
    paste_pairs: list[PastePairIn] = Field(default_factory=list, max_length=500)
    # Optional FAQ database (encrypted on the server; not returned in the embed snippet).
    sql_dsn: str | None = Field(default=None, max_length=2000)
    sql_query: str | None = Field(default=None, max_length=8000)
    sql_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "question_raw": "q",
            "official_answer": "a",
            "owner_office": "office_name",
        }
    )
    # Optional FAQ HTTP API
    rest_url: str | None = Field(default=None, max_length=2000)
    rest_items_path: str = Field(default="items", max_length=128)
    rest_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "question_raw": "question",
            "official_answer": "answer",
            "owner_office": "office",
        }
    )
    # Optional public website to mine draft Q&A from
    website_start_url: str | None = Field(default=None, max_length=2000)
    website_max_pages: int = Field(default=15, ge=1, le=50)


class OnboardResult(BaseModel):
    tenant_id: UUID
    slug: str
    plan: str
    widget_key: str
    embed_snippet: str
    admin_email: EmailStr
    offices_created: int
    message: str
    knowledge_source: str = "demo"
    answers_loaded: int = 0
    connector_created: bool = False
    sync_stats: dict[str, Any] | None = None


class ExternalAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="en", max_length=8)


class ExternalAskOut(BaseModel):
    reply: str
    decision: str
    trace_id: str
    source: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    estimated_cost_usd: float = 0.0
