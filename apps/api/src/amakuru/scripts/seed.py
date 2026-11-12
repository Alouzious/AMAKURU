"""Bootstrap platform admin and optional demo tenant.

Demo data is plainly labelled as demonstration content.
Never invents real university fees, dates, or contacts.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import dispose_engine, get_session_factory, set_tenant
from amakuru.core.logging import configure_logging, get_logger
from amakuru.core.settings import get_settings
from amakuru.modules.channels.keys import hash_widget_key, widget_key_prefix
from amakuru.modules.channels.models import DEFAULT_QUICK_TOPICS, ChannelConfig
from amakuru.modules.evaluation.loader import load_golden_jsonl
from amakuru.modules.identity.models import (
    ROLE_OFFICE_APPROVER,
    ROLE_OFFICE_EDITOR,
    ROLE_TENANT_ADMIN,
    Membership,
    User,
)
from amakuru.modules.identity.service import create_user, get_user_by_email
from amakuru.modules.knowledge.models import (
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    Office,
    QuestionVariant,
)
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.retrieval.indexing import index_tenant
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.vector_store import PgVectorStore
from amakuru.modules.tenancy.models import Tenant

DEMO_WIDGET_KEY = "ak_live_demo_university_key_change_me"
DEMO_B_WIDGET_KEY = "ak_live_demo_college_key_change_me"

logger = get_logger("amakuru.seed")

DEMO_SLUG = "demo-university"
DEMO_B_SLUG = "demo-college"
DEMO_LABEL = (
    "DEMONSTRATION CONTENT ONLY — not affiliated with any real university. "
    "Do not treat names, programmes, or contacts as factual."
)
DEMO_EDITOR_EMAIL = "editor@example.com"
DEMO_APPROVER_EMAIL = "approver@example.com"
DEMO_STAFF_PASSWORD = "ChangeMeNow123!"
DEMO_B_ADMIN_EMAIL = "college-admin@example.com"


async def ensure_bootstrap_admin(session: AsyncSession) -> User:
    settings = get_settings()
    existing = await get_user_by_email(session, settings.bootstrap_admin_email)
    if existing:
        if not existing.is_platform_admin:
            existing.is_platform_admin = True
        logger.info("bootstrap_admin_exists", email=existing.email)
        return existing

    user = await create_user(
        session,
        email=settings.bootstrap_admin_email,
        password=settings.bootstrap_admin_password,
        full_name="Platform Administrator",
        is_platform_admin=True,
    )
    await write_audit(
        session,
        action="seed.bootstrap_admin",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        detail={"email": user.email},
    )
    logger.info("bootstrap_admin_created", email=user.email)
    return user


async def _ensure_user(session: AsyncSession, *, email: str, full_name: str, password: str) -> User:
    existing = await get_user_by_email(session, email)
    if existing:
        return existing
    return await create_user(
        session, email=email, password=password, full_name=full_name, is_platform_admin=False
    )


async def _ensure_membership(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    office_id: uuid.UUID | None = None,
) -> None:
    q = select(Membership).where(
        Membership.tenant_id == tenant_id,
        Membership.user_id == user_id,
        Membership.role == role,
    )
    if office_id is None:
        q = q.where(Membership.office_id.is_(None))
    else:
        q = q.where(Membership.office_id == office_id)
    if (await session.execute(q)).scalar_one_or_none() is None:
        session.add(
            Membership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                office_id=office_id,
            )
        )
        await session.flush()


async def ensure_demo_tenant(session: AsyncSession, admin: User) -> Tenant | None:
    settings = get_settings()
    if not settings.seed_demo_data:
        logger.info("demo_seed_skipped")
        return None

    result = await session.execute(select(Tenant).where(Tenant.slug == DEMO_SLUG))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Demo University (Demonstration)",
            slug=DEMO_SLUG,
            branding={"accent": "#0F4C5C", "label": "demo"},
            default_language="en",
            plan=settings.default_plan,
            status="active",
            residency_mode="hosted",
            is_demo=True,
            demo_label=DEMO_LABEL,
        )
        session.add(tenant)
        await session.flush()
        await write_audit(
            session,
            action="seed.demo_tenant",
            resource_type="tenant",
            resource_id=str(tenant.id),
            tenant_id=tenant.id,
            actor_user_id=admin.id,
            detail={"slug": DEMO_SLUG, "warning": DEMO_LABEL},
        )
        logger.info("demo_tenant_created", slug=DEMO_SLUG)
    else:
        logger.info("demo_tenant_exists", slug=DEMO_SLUG)

    await set_tenant(session, tenant.id)
    await _ensure_membership(session, tenant_id=tenant.id, user_id=admin.id, role=ROLE_TENANT_ADMIN)

    offices: dict[str, Office] = {}
    for name in ("Registrar", "Admissions", "Finance"):
        existing = await session.execute(
            select(Office).where(
                Office.tenant_id == tenant.id, Office.name == name, Office.deleted_at.is_(None)
            )
        )
        office = existing.scalar_one_or_none()
        if office is None:
            office = Office(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name=name,
                contact_person=f"Demo {name} Contact",
                phone="+000-000-0000",
                email=f"{name.lower()}@demo.example",
                opening_hours="Mon–Fri 09:00–16:00 (demonstration)",
            )
            session.add(office)
            await session.flush()
        offices[name] = office

    editor = await _ensure_user(
        session,
        email=DEMO_EDITOR_EMAIL,
        full_name="Demo Editor",
        password=DEMO_STAFF_PASSWORD,
    )
    approver = await _ensure_user(
        session,
        email=DEMO_APPROVER_EMAIL,
        full_name="Demo Approver",
        password=DEMO_STAFF_PASSWORD,
    )
    registrar = offices["Registrar"]
    await _ensure_membership(
        session,
        tenant_id=tenant.id,
        user_id=editor.id,
        role=ROLE_OFFICE_EDITOR,
        office_id=registrar.id,
    )
    await _ensure_membership(
        session,
        tenant_id=tenant.id,
        user_id=approver.id,
        role=ROLE_OFFICE_APPROVER,
        office_id=registrar.id,
    )

    demo_specs: list[tuple[str, Office, bool, str, str, list[str]]] = [
        (
            "welcome",
            registrar,
            True,
            "DEMONSTRATION ONLY: This is a sample answer for Demo University. "
            "It is not real institutional information.",
            "What is this demo chatbot for?",
            ["whats this demo bot about"],
        ),
        (
            "registration",
            registrar,
            True,
            "DEMONSTRATION ONLY: Registration guidance is fictional for this sample dataset.",
            "Where do I find demonstration registration info?",
            ["how do i register in the demo"],
        ),
        (
            "admissions",
            offices["Admissions"],
            False,
            "DEMONSTRATION ONLY: Application steps shown here are not real.",
            "How do I apply in this demo?",
            ["demo application steps please"],
        ),
    ]

    for subcategory, target_office, verbatim_only, answer_text, question_text, extras in demo_specs:
        found = await session.execute(
            select(AnswerEntry)
            .where(
                AnswerEntry.tenant_id == tenant.id,
                AnswerEntry.category == "demo",
                AnswerEntry.subcategory == subcategory,
                AnswerEntry.deleted_at.is_(None),
            )
            .order_by(AnswerEntry.created_at.asc())
        )
        matches = list(found.scalars().all())
        keep = matches[0] if matches else None
        for dup in matches[1:]:
            dup.deleted_at = datetime.now(UTC)
        if keep is None:
            keep = AnswerEntry(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                office_id=target_office.id,
                category="demo",
                subcategory=subcategory,
                verbatim_only=verbatim_only,
                escalate_to_human=False,
                applicability={},
            )
            session.add(keep)
            await session.flush()
            session.add(
                AnswerVersion(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    entry_id=keep.id,
                    version_number=1,
                    answer_text=answer_text,
                    source_document="demo-seed",
                    last_verified=date.today(),
                    valid_until=date.today() + timedelta(days=90),
                    status=STATUS_PUBLISHED,
                    editor_id=editor.id,
                    approver_id=approver.id,
                    published_at=datetime.now(UTC),
                )
            )
            session.add(
                QuestionVariant(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    entry_id=keep.id,
                    raw_text=question_text,
                    language="en",
                    asker_type="student",
                    channel="widget",
                )
            )
            await session.flush()
        else:
            ver = await session.execute(
                select(AnswerVersion).where(
                    AnswerVersion.entry_id == keep.id,
                    AnswerVersion.status == STATUS_PUBLISHED,
                )
            )
            if ver.scalars().first() is None:
                draft = await session.execute(
                    select(AnswerVersion)
                    .where(AnswerVersion.entry_id == keep.id)
                    .order_by(AnswerVersion.version_number.desc())
                )
                latest = draft.scalars().first()
                if latest and latest.status == STATUS_DRAFT:
                    latest.status = STATUS_PUBLISHED
                    latest.approver_id = approver.id
                    await session.flush()
        # Extra paraphrase variants for eval paraphrases
        for extra in extras:
            exists_q = await session.execute(
                select(QuestionVariant).where(
                    QuestionVariant.entry_id == keep.id,
                    QuestionVariant.raw_text == extra,
                )
            )
            if exists_q.scalars().first() is None:
                session.add(
                    QuestionVariant(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        entry_id=keep.id,
                        raw_text=extra,
                        language="en",
                        asker_type="student",
                        channel="widget",
                    )
                )
        await session.flush()
    # Keep an unpublished draft for governance demos.
    draft_only = await session.execute(
        select(AnswerEntry).where(
            AnswerEntry.tenant_id == tenant.id,
            AnswerEntry.subcategory == "governance-draft",
        )
    )
    if draft_only.scalar_one_or_none() is None:
        draft_entry = AnswerEntry(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            office_id=registrar.id,
            category="demo",
            subcategory="governance-draft",
            verbatim_only=True,
        )
        session.add(draft_entry)
        await session.flush()
        session.add(
            AnswerVersion(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                entry_id=draft_entry.id,
                version_number=1,
                answer_text="DEMONSTRATION ONLY: unpublished draft.",
                status=STATUS_DRAFT,
                editor_id=editor.id,
            )
        )
        await session.flush()

    ch = await session.execute(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant.id))
    if ch.scalar_one_or_none() is None:
        session.add(
            ChannelConfig(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                widget_key_hash=hash_widget_key(DEMO_WIDGET_KEY),
                widget_key_prefix=widget_key_prefix(DEMO_WIDGET_KEY),
                allowed_origins=[
                    "http://localhost:8000",
                    "http://127.0.0.1:8000",
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "*",
                ],
                whatsapp_enabled=False,
                quick_topics=DEFAULT_QUICK_TOPICS,
                welcome_message=(
                    "DEMONSTRATION ONLY — ask about Admissions, Fees, Calendar, "
                    "Registration, or Services."
                ),
            )
        )
        await session.flush()
        logger.info(
            "demo_channel_config_created", widget_key_prefix=widget_key_prefix(DEMO_WIDGET_KEY)
        )

    golden_path = Path(__file__).resolve().parents[5] / "eval" / "demo" / "golden.jsonl"
    # parents: scripts(0)->amakuru(1)->src(2)->api(3)->apps(4)->repo(5)
    if not golden_path.exists():
        golden_path = Path.cwd().parents[1] / "eval" / "demo" / "golden.jsonl"
    if not golden_path.exists():
        golden_path = Path("/home/codeguru/AMAKURU/eval/demo/golden.jsonl")
    loaded = await load_golden_jsonl(session, tenant_id=tenant.id, path=golden_path)
    logger.info("golden_loaded", count=loaded, path=str(golden_path))

    embedder = build_embedding_provider(settings)
    store = PgVectorStore()
    stats = await index_tenant(
        session,
        tenant_id=tenant.id,
        embedder=embedder,
        store=store,
        settings=settings,
    )
    logger.info("demo_indexed", **stats)

    await set_tenant(session, None)
    return tenant


async def ensure_second_demo_tenant(session: AsyncSession, admin: User) -> Tenant | None:
    """Second demonstration university for multi-tenant isolation demos (Phase 7)."""
    settings = get_settings()
    if not settings.seed_demo_data:
        return None

    from amakuru.modules.billing.router import ensure_plans_seeded

    await ensure_plans_seeded(session)

    result = await session.execute(select(Tenant).where(Tenant.slug == DEMO_B_SLUG))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Demo College (Demonstration)",
            slug=DEMO_B_SLUG,
            branding={
                "accent": "#7C2D12",
                "label": "demo",
                "display_name": "Demo College",
            },
            default_language="en",
            plan="campus",
            status="active",
            residency_mode="hosted",
            is_demo=True,
            demo_label=DEMO_LABEL,
        )
        session.add(tenant)
        await session.flush()
        await write_audit(
            session,
            action="seed.demo_tenant_b",
            resource_type="tenant",
            resource_id=str(tenant.id),
            tenant_id=tenant.id,
            actor_user_id=admin.id,
            detail={"slug": DEMO_B_SLUG, "warning": DEMO_LABEL},
        )
        logger.info("demo_college_created", slug=DEMO_B_SLUG)
    else:
        logger.info("demo_college_exists", slug=DEMO_B_SLUG)

    await set_tenant(session, tenant.id)
    await _ensure_membership(session, tenant_id=tenant.id, user_id=admin.id, role=ROLE_TENANT_ADMIN)

    college_admin = await _ensure_user(
        session,
        email=DEMO_B_ADMIN_EMAIL,
        full_name="Demo College Admin",
        password=DEMO_STAFF_PASSWORD,
    )
    await _ensure_membership(
        session, tenant_id=tenant.id, user_id=college_admin.id, role=ROLE_TENANT_ADMIN
    )

    office_q = await session.execute(
        select(Office).where(
            Office.tenant_id == tenant.id, Office.name == "Registrar", Office.deleted_at.is_(None)
        )
    )
    office = office_q.scalar_one_or_none()
    if office is None:
        office = Office(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Registrar",
            contact_person="Demo College Registrar",
            phone="+000-111-0000",
            email="registrar@demo-college.example",
            opening_hours="Mon–Fri 08:00–15:00 (demonstration)",
        )
        session.add(office)
        await session.flush()

    entry_q = await session.execute(
        select(AnswerEntry).where(
            AnswerEntry.tenant_id == tenant.id,
            AnswerEntry.subcategory == "college-welcome",
            AnswerEntry.deleted_at.is_(None),
        )
    )
    if entry_q.scalar_one_or_none() is None:
        entry = AnswerEntry(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            office_id=office.id,
            category="demo",
            subcategory="college-welcome",
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
                answer_text=(
                    "DEMONSTRATION ONLY: This is Demo College's private answer bank. "
                    "It must never appear for Demo University."
                ),
                source_document="demo-seed-college",
                last_verified=date.today(),
                valid_until=date.today() + timedelta(days=90),
                status=STATUS_PUBLISHED,
                editor_id=college_admin.id,
                approver_id=admin.id,
                published_at=datetime.now(UTC),
            )
        )
        session.add(
            QuestionVariant(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                entry_id=entry.id,
                raw_text="What is Demo College's chatbot for?",
                language="en",
                asker_type="student",
                channel="widget",
            )
        )
        await session.flush()

    ch = await session.execute(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant.id))
    if ch.scalar_one_or_none() is None:
        session.add(
            ChannelConfig(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                widget_key_hash=hash_widget_key(DEMO_B_WIDGET_KEY),
                widget_key_prefix=widget_key_prefix(DEMO_B_WIDGET_KEY),
                allowed_origins=["*"],
                whatsapp_enabled=False,
                quick_topics=DEFAULT_QUICK_TOPICS,
                welcome_message="DEMONSTRATION ONLY — Demo College widget.",
            )
        )
        await session.flush()

    embedder = build_embedding_provider(settings)
    store = PgVectorStore()
    await index_tenant(
        session,
        tenant_id=tenant.id,
        embedder=embedder,
        store=store,
        settings=settings,
    )
    await set_tenant(session, None)
    return tenant


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    factory = get_session_factory(settings)
    async with factory() as session, session.begin():
        from amakuru.modules.billing.router import ensure_plans_seeded

        await ensure_plans_seeded(session)
        admin = await ensure_bootstrap_admin(session)
        await ensure_demo_tenant(session, admin)
        await ensure_second_demo_tenant(session, admin)
    await dispose_engine()
    print("Seed complete.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
