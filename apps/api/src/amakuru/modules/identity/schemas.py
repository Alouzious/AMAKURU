"""Identity API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class MembershipOut(BaseModel):
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: str
    office_id: UUID | None = None
    is_demo: bool = False


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    is_platform_admin: bool
    totp_enabled: bool = False
    memberships: list[MembershipOut]
    csrf_token: str | None = None


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_url: str
    qr_data_url: str


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class LoginResponse(BaseModel):
    user: UserOut
    message: str = "Logged in"


class MessageOut(BaseModel):
    message: str


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    status: str
    residency_mode: str = "hosted"
    default_language: str
    is_demo: bool
    demo_label: str | None
    branding: dict[str, object] = {}
    created_at: datetime
