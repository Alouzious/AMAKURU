"""Tenant onboarding wizard — creates tenant, admin, offices, widget key, optional knowledge source."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import set_tenant
from amakuru.core.errors import ValidationAppError
from amakuru.core.logging import get_logger
from amakuru.core.security import encrypt_secret
from amakuru.core.settings import Settings
from amakuru.modules.billing.catalog import PLAN_CATALOG
from amakuru.modules.billing.schemas import OfficeSeedIn, OnboardRequest, OnboardResult
from amakuru.modules.channels.keys import generate_widget_key, hash_widget_key, widget_key_prefix
from amakuru.modules.channels.models import DEFAULT_QUICK_TOPICS, ChannelConfig
from amakuru.modules.identity.models import ROLE_TENANT_ADMIN, Membership, User
from amakuru.modules.identity.service import create_user, get_user_by_email
from amakuru.modules.knowledge.models import (
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    Connector,
    Office,
    QuestionVariant,
)
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.tenancy.models import Tenant

logger = get_logger("amakuru.onboarding")

DEMO_ANSWER = (
    "DEMONSTRATION ONLY: This answer was created by the onboarding wizard. "
    "Replace it with office-approved content before go-live."
)


def _slugify_subcategory(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:48] or fallback)[:48]


async def _publish_qa(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    office: Office,
    editor: User,
    subcategory: str,
    question: str,
    answer: str,
    source_document: str,
) -> None:
    entry = AnswerEntry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        office_id=office.id,
        category="imported",
        subcategory=subcategory,
        verbatim_only=True,
        escalate_to_human=False,
        applicability={},
    )
    session.add(entry)
    await session.flush()
    session.add(
        AnswerVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entry_id=entry.id,
            version_number=1,
            answer_text=answer,
            source_document=source_document,
            last_verified=date.today(),
            valid_until=date.today() + timedelta(days=90),
            status=STATUS_PUBLISHED,
            editor_id=editor.id,
            approver_id=editor.id,
            published_at=datetime.now(UTC),
        )
    )
    session.add(
        QuestionVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entry_id=entry.id,
            raw_text=question,
            language="en",
            asker_type="student",
            channel="import",
        )
    )
    await session.flush()


async def _office_by_name(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str | None,
    fallback: Office,
) -> Office:
    if not name:
        return fallback
    result = await session.execute(
        select(Office).where(
            Office.tenant_id == tenant_id,
            Office.name == name,
            Office.deleted_at.is_(None),
        )
    )
    found = result.scalar_one_or_none()
    if found:
        return found
    office = Office(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        contact_person=f"{name} contact",
        phone="+000-000-0000",
        email=f"{name.lower().replace(' ', '.')}@example.local",
        opening_hours="Mon–Fri 09:00–16:00",
    )
    session.add(office)
    await session.flush()
    return office


async def onboard_tenant(
    session: AsyncSession,
    *,
    body: OnboardRequest,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> OnboardResult:
    if body.plan not in PLAN_CATALOG:
        raise ValidationAppError(f"Unknown plan '{body.plan}'")

    source = body.knowledge_source
    if body.seed_demo_answers and source == "none":
        source = "demo"
    if source == "paste" and not body.paste_pairs:
        raise ValidationAppError("Paste at least one question and answer, or choose another source")
    if source == "sql_db" and (not body.sql_dsn or not body.sql_query):
        raise ValidationAppError("SQL source requires sql_dsn and sql_query")
    if source == "rest_json" and not body.rest_url:
        raise ValidationAppError("API source requires rest_url")
    if source == "website" and not body.website_start_url:
        raise ValidationAppError("Website source requires website_start_url")

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
            "DEMONSTRATION CONTENT ONLY — not affiliated with any real organization."
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

    origins = [o.strip() for o in body.allowed_origins if o and o.strip()]
    if body.site_origin and body.site_origin.strip():
        origin = body.site_origin.strip().rstrip("/")
        if origin not in origins and "*" not in origins:
            origins.append(origin)
    if not origins:
        origins = ["*"]

    raw_widget = generate_widget_key()
    session.add(
        ChannelConfig(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            widget_key_hash=hash_widget_key(raw_widget),
            widget_key_prefix=widget_key_prefix(raw_widget),
            allowed_origins=origins,
            whatsapp_enabled=False,
            quick_topics=DEFAULT_QUICK_TOPICS,
            welcome_message=f"Welcome to {body.name}. Ask about admissions, fees, or services.",
        )
    )

    answers_loaded = 0
    connector_created = False
    sync_stats: dict[str, Any] | None = None
    notes: list[str] = []

    if source in {"demo", None} or (body.seed_demo_answers and source == "demo"):
        if first_office is not None and source == "demo":
            await _publish_qa(
                session,
                tenant_id=tenant.id,
                office=first_office,
                editor=user,
                subcategory="welcome",
                question=f"What can {body.name} help me with?",
                answer=DEMO_ANSWER,
                source_document="onboarding-wizard",
            )
            answers_loaded = 1
            notes.append("Loaded 1 demonstration answer. Replace before go-live.")

    if source == "paste" and first_office is not None:
        for i, pair in enumerate(body.paste_pairs):
            office = await _office_by_name(
                session,
                tenant_id=tenant.id,
                name=pair.office,
                fallback=first_office,
            )
            await _publish_qa(
                session,
                tenant_id=tenant.id,
                office=office,
                editor=user,
                subcategory=_slugify_subcategory(pair.question, f"pair-{i + 1}"),
                question=pair.question.strip(),
                answer=pair.answer.strip(),
                source_document="onboarding-paste",
            )
            answers_loaded += 1
        notes.append(f"Published {answers_loaded} Q&A pairs they shared with you.")

    if source in {"sql_db", "rest_json", "website"} and first_office is not None:
        config: dict[str, Any]
        mapping: dict[str, str]
        if source == "sql_db":
            assert body.sql_dsn and body.sql_query
            config = {"dsn": body.sql_dsn.strip(), "query": body.sql_query.strip()}
            mapping = {str(k): str(v) for k, v in body.sql_mapping.items()}
            name = f"{body.name} FAQ database"
        elif source == "rest_json":
            assert body.rest_url
            config = {
                "url": body.rest_url.strip(),
                "items_path": body.rest_items_path or "items",
            }
            mapping = {str(k): str(v) for k, v in body.rest_mapping.items()}
            name = f"{body.name} FAQ API"
        else:
            assert body.website_start_url
            config = {
                "start_url": body.website_start_url.strip(),
                "max_pages": body.website_max_pages,
                "default_office": first_office.name,
            }
            mapping = {
                "question_raw": "question_raw",
                "official_answer": "official_answer",
                "owner_office": "owner_office",
            }
            name = f"{body.name} website"

        connector = Connector(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=name,
            adapter_type=source,
            config_encrypted=encrypt_secret(settings, json.dumps(config)),
            field_mapping=mapping,
            schedule_cron="auto",
            is_active=True,
        )
        session.add(connector)
        await session.flush()
        connector_created = True
        notes.append("Saved their data source (encrypted). It is not in the public snippet.")

        try:
            from amakuru.modules.knowledge.sync import sync_connector

            sync_stats = await sync_connector(
                session,
                connector=connector,
                settings=settings,
                actor_id=user.id,
                default_office_id=first_office.id,
            )
            drafts = int(sync_stats.get("drafts_created") or 0)
            answers_loaded += drafts
            notes.append(
                f"First sync: {drafts} drafts, "
                f"{sync_stats.get('needs_answer', 0)} need answers, "
                f"{sync_stats.get('errors', 0)} row errors. Review drafts before publish."
            )
        except Exception as exc:  # noqa: BLE001 — org still created; sync can retry later
            logger.warning("onboard_sync_failed", error=str(exc), slug=body.slug)
            notes.append(
                f"Connector saved but first sync failed ({exc}). "
                "Fix credentials in Connectors and sync again."
            )

    if source == "none":
        notes.append("Answer bank is empty — add answers in the dashboard before go-live.")

    if answers_loaded > 0 and source in {"demo", "paste"}:
        try:
            from amakuru.modules.retrieval.indexing import index_tenant
            from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
            from amakuru.modules.retrieval.vector_store import PgVectorStore

            stats = await index_tenant(
                session,
                tenant_id=tenant.id,
                embedder=build_embedding_provider(settings),
                store=PgVectorStore(),
                settings=settings,
            )
            notes.append(f"Indexed for search ({stats.get('indexed', 0)} vectors).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("onboard_index_failed", error=str(exc), slug=body.slug)
            notes.append("Answers saved; indexing can be re-run later from the worker.")

    await write_audit(
        session,
        action="onboarding.tenant_created",
        resource_type="tenant",
        resource_id=str(tenant.id),
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        detail={
            "slug": body.slug,
            "plan": body.plan,
            "is_demo": body.is_demo,
            "knowledge_source": source,
            "answers_loaded": answers_loaded,
            "connector_created": connector_created,
        },
    )
    await session.flush()

    api_base = settings.api_base_url.rstrip("/")
    snippet = (
        f'<script>\n'
        f'  window.AmakuruConfig = {{\n'
        f'    apiBase: "{api_base}",\n'
        f'    key: "{raw_widget}",\n'
        f'    language: "{body.default_language}"\n'
        f'  }};\n'
        f'</script>\n'
        f'<script src="{api_base}/widget/amakuru-widget.js" defer></script>'
    )
    message = (
        "Organization created. Copy the widget key and snippet now — "
        "the full key is shown once. Give only the snippet to the organization; "
        "it contains no database secrets. "
        + " ".join(notes)
    )
    return OnboardResult(
        tenant_id=tenant.id,
        slug=tenant.slug,
        plan=tenant.plan,
        widget_key=raw_widget,
        embed_snippet=snippet,
        admin_email=body.admin_email,
        offices_created=offices_created,
        message=message,
        knowledge_source=source,
        answers_loaded=answers_loaded,
        connector_created=connector_created,
        sync_stats=sync_stats,
    )
