"""Tenant onboarding wizard — creates tenant, admin, offices, widget key."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import set_tenant
from amakuru.core.errors import ValidationAppError
from amakuru.core.settings import Settings
from amakuru.modules.billing.catalog import PLAN_CATALOG
from amakuru.modules.billing.schemas import OfficeSeedIn, OnboardRequest, OnboardResult
from amakuru.modules.channels.keys import generate_widget_key, hash_widget_key, widget_key_prefix
from amakuru.modules.channels.models import DEFAULT_QUICK_TOPICS, ChannelConfig
from amakuru.modules.identity.models import ROLE_TENANT_ADMIN, Membership
from amakuru.modules.identity.service import create_user, get_user_by_email
from amakuru.modules.knowledge.models import STATUS_PUBLISHED, AnswerEntry, AnswerVersion, Office
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.tenancy.models import Tenant

DEMO_ANSWER = (
    "DEMONSTRATION ONLY: This answer was created by the onboarding wizard. "
    "Replace it with office-approved content before go-live."
)


async def onboard_tenant(
    session: AsyncSession,
    *,
    body: OnboardRequest,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> OnboardResult:
    if body.plan not in PLAN_CATALOG:
        raise ValidationAppError(f"Unknown plan '{body.plan}'")

    existing = await session.execute(select(Tenant).where(Tenant.slug == body.slug))
    if existing.scalar_one_or_none() is not None:
        raise ValidationAppError(f"Slug '{body.slug}' is already taken")

    tenant = Tenant(
        id=uuid.uuid4(),
        name=body.name,
        slug=body.slug,
        branding={
            "accent": body.accent,
            "label": "demo" if body.is_demo else "live",
            "display_name": body.name,
        },
        default_language=body.default_language,
        plan=body.plan,
        status="active",
        residency_mode=body.residency_mode,
        is_demo=body.is_demo,
        demo_label=(
            "DEMONSTRATION CONTENT ONLY — not affiliated with any real university."
            if body.is_demo
            else None
        ),
    )
    session.add(tenant)
    await session.flush()

    await set_tenant(session, tenant.id)

    user = await get_user_by_email(session, body.admin_email)
    if user is None:
        user = await create_user(
            session,
            email=body.admin_email,
            password=body.admin_password,
            full_name=body.admin_full_name,
            is_platform_admin=False,
        )
    session.add(
        Membership(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id=user.id,
            role=ROLE_TENANT_ADMIN,
            office_id=None,
        )
    )

    offices: list[OfficeSeedIn] = list(body.offices) or [
        OfficeSeedIn(name="Registrar"),
        OfficeSeedIn(name="Admissions"),
        OfficeSeedIn(name="Finance"),
    ]
    offices_created = 0
    first_office: Office | None = None
    for spec in offices:
        office = Office(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=spec.name,
            contact_person=spec.contact_person or f"{spec.name} contact",
            phone=spec.phone or "+000-000-0000",
            email=spec.email or f"{spec.name.lower().replace(' ', '.')}@{body.slug}.example",
            opening_hours=spec.opening_hours or "Mon–Fri 09:00–16:00",
        )
        session.add(office)
        await session.flush()
        offices_created += 1
        if first_office is None:
            first_office = office

    raw_widget = generate_widget_key()
    session.add(
        ChannelConfig(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            widget_key_hash=hash_widget_key(raw_widget),
            widget_key_prefix=widget_key_prefix(raw_widget),
            allowed_origins=["*"],
            whatsapp_enabled=False,
            quick_topics=DEFAULT_QUICK_TOPICS,
            welcome_message=f"Welcome to {body.name}. Ask about admissions, fees, or services.",
        )
    )

    if body.seed_demo_answers and first_office is not None:
        entry = AnswerEntry(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            office_id=first_office.id,
            category="demo",
            subcategory="welcome",
            verbatim_only=True,
            escalate_to_human=False,
            applicability={},
        )
        session.add(entry)
        await session.flush()
        session.add(
            AnswerVersion(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                entry_id=entry.id,
                version_number=1,
                answer_text=DEMO_ANSWER,
                source_document="onboarding-wizard",
                last_verified=date.today(),
                valid_until=date.today() + timedelta(days=90),
                status=STATUS_PUBLISHED,
                editor_id=user.id,
                approver_id=user.id,
                published_at=datetime.now(UTC),
            )
        )

    await write_audit(
        session,
        action="onboarding.tenant_created",
        resource_type="tenant",
        resource_id=str(tenant.id),
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        detail={"slug": body.slug, "plan": body.plan, "is_demo": body.is_demo},
    )
    await session.flush()

    api_base = settings.api_base_url.rstrip("/")
    snippet = (
        f'<script>window.AmakuruConfig={{apiBase:"{api_base}",'
        f'key:"{raw_widget}",language:"{body.default_language}"}};'
        f"</script>\n"
        f'<script src="{api_base}/widget/amakuru-widget.js" defer></script>'
    )
    return OnboardResult(
        tenant_id=tenant.id,
        slug=tenant.slug,
        plan=tenant.plan,
        widget_key=raw_widget,
        embed_snippet=snippet,
        admin_email=body.admin_email,
        offices_created=offices_created,
        message="Tenant onboarded. Share the widget key securely; it is shown once.",
    )
