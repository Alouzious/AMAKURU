"""Knowledge governance service."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from amakuru.core.settings import Settings
from amakuru.modules.identity.models import Membership, User
from amakuru.modules.knowledge.deps import can_approve_office, can_edit_office, load_memberships
from amakuru.modules.knowledge.models import (
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_IN_REVIEW,
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    NeedsAnswerItem,
    Office,
    QuestionVariant,
)
from amakuru.modules.knowledge.schemas import (
    EntryCreate,
    EntryOut,
    NeedsAnswerOut,
    OfficeCreate,
    OfficeOut,
    OfficeUpdate,
    VersionCreate,
    VersionOut,
)
from amakuru.modules.platform.audit import write_audit


def _office_out(o: Office) -> OfficeOut:
    return OfficeOut(
        id=o.id,
        tenant_id=o.tenant_id,
        name=o.name,
        contact_person=o.contact_person,
        phone=o.phone,
        email=o.email,
        opening_hours=o.opening_hours,
        created_at=o.created_at,
    )


def _version_out(v: AnswerVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        entry_id=v.entry_id,
        version_number=v.version_number,
        answer_text=v.answer_text,
        source_document=v.source_document,
        last_verified=v.last_verified,
        valid_from=v.valid_from,
        valid_until=v.valid_until,
        status=v.status,
        editor_id=v.editor_id,
        approver_id=v.approver_id,
        approved_at=v.approved_at,
        published_at=v.published_at,
        created_at=v.created_at,
    )


async def _latest_version(session: AsyncSession, entry_id: uuid.UUID) -> AnswerVersion | None:
    result = await session.execute(
        select(AnswerVersion)
        .where(AnswerVersion.entry_id == entry_id)
        .order_by(AnswerVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _entry_out(session: AsyncSession, entry: AnswerEntry) -> EntryOut:
    latest = await _latest_version(session, entry.id)
    return EntryOut(
        id=entry.id,
        tenant_id=entry.tenant_id,
        office_id=entry.office_id,
        category=entry.category,
        subcategory=entry.subcategory,
        verbatim_only=entry.verbatim_only,
        escalate_to_human=entry.escalate_to_human,
        applicability=entry.applicability or {},
        season=entry.season,
        created_at=entry.created_at,
        latest_version=_version_out(latest) if latest else None,
    )


async def create_office(
    session: AsyncSession, *, tenant_id: uuid.UUID, body: OfficeCreate, actor: User
) -> OfficeOut:
    office = Office(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=body.name,
        contact_person=body.contact_person,
        phone=body.phone,
        email=body.email,
        opening_hours=body.opening_hours,
    )
    session.add(office)
    await session.flush()
    await write_audit(
        session,
        action="office.create",
        resource_type="office",
        resource_id=str(office.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        detail={"name": office.name},
    )
    return _office_out(office)


async def list_offices(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[OfficeOut]:
    result = await session.execute(
        select(Office)
        .where(Office.tenant_id == tenant_id, Office.deleted_at.is_(None))
        .order_by(Office.name)
    )
    return [_office_out(o) for o in result.scalars().all()]


async def update_office(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    office_id: uuid.UUID,
    body: OfficeUpdate,
    actor: User,
) -> OfficeOut:
    office = await _get_office(session, tenant_id, office_id)
    for field in ("name", "contact_person", "phone", "email", "opening_hours"):
        value = getattr(body, field)
        if value is not None:
            setattr(office, field, value)
    await session.flush()
    await write_audit(
        session,
        action="office.update",
        resource_type="office",
        resource_id=str(office.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return _office_out(office)


async def _get_office(session: AsyncSession, tenant_id: uuid.UUID, office_id: uuid.UUID) -> Office:
    result = await session.execute(
        select(Office).where(
            Office.id == office_id, Office.tenant_id == tenant_id, Office.deleted_at.is_(None)
        )
    )
    office = result.scalar_one_or_none()
    if office is None:
        raise NotFoundError("Office not found")
    return office


async def create_entry(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    body: EntryCreate,
    actor: User,
) -> EntryOut:
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_edit_office(memberships, body.office_id, is_platform_admin=actor.is_platform_admin):
        raise ForbiddenError("Not allowed to edit this office")
    await _get_office(session, tenant_id, body.office_id)

    entry = AnswerEntry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        office_id=body.office_id,
        category=body.category,
        subcategory=body.subcategory,
        verbatim_only=body.verbatim_only,
        escalate_to_human=body.escalate_to_human,
        applicability=body.applicability,
        season=body.season,
    )
    session.add(entry)
    await session.flush()

    version = AnswerVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entry_id=entry.id,
        version_number=1,
        answer_text=body.answer_text,
        source_document=body.source_document,
        last_verified=body.last_verified,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        status=STATUS_DRAFT,
        editor_id=actor.id,
    )
    session.add(version)
    await session.flush()

    if body.question_raw:
        session.add(
            QuestionVariant(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                entry_id=entry.id,
                raw_text=body.question_raw,
                language=body.language,
                asker_type=body.asker_type,
                channel=body.channel,
            )
        )

    await write_audit(
        session,
        action="answer.create",
        resource_type="answer_entry",
        resource_id=str(entry.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return await _entry_out(session, entry)


async def list_entries(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[EntryOut]:
    result = await session.execute(
        select(AnswerEntry)
        .where(AnswerEntry.tenant_id == tenant_id, AnswerEntry.deleted_at.is_(None))
        .order_by(AnswerEntry.created_at.desc())
    )
    return [await _entry_out(session, e) for e in result.scalars().all()]


async def get_entry(
    session: AsyncSession, *, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> EntryOut:
    entry = await _get_entry(session, tenant_id, entry_id)
    return await _entry_out(session, entry)


async def _get_entry(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> AnswerEntry:
    result = await session.execute(
        select(AnswerEntry).where(
            AnswerEntry.id == entry_id,
            AnswerEntry.tenant_id == tenant_id,
            AnswerEntry.deleted_at.is_(None),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Answer entry not found")
    return entry


async def _get_version(
    session: AsyncSession, tenant_id: uuid.UUID, version_id: uuid.UUID
) -> AnswerVersion:
    result = await session.execute(
        select(AnswerVersion).where(
            AnswerVersion.id == version_id, AnswerVersion.tenant_id == tenant_id
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundError("Answer version not found")
    return version


async def add_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: VersionCreate,
    actor: User,
) -> VersionOut:
    entry = await _get_entry(session, tenant_id, entry_id)
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_edit_office(memberships, entry.office_id, is_platform_admin=actor.is_platform_admin):
        raise ForbiddenError("Not allowed to edit this office")

    max_num = await session.execute(
        select(func.coalesce(func.max(AnswerVersion.version_number), 0)).where(
            AnswerVersion.entry_id == entry_id
        )
    )
    next_num = int(max_num.scalar_one()) + 1
    version = AnswerVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entry_id=entry_id,
        version_number=next_num,
        answer_text=body.answer_text,
        source_document=body.source_document,
        last_verified=body.last_verified,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        status=STATUS_DRAFT,
        editor_id=actor.id,
    )
    session.add(version)
    await session.flush()
    await write_audit(
        session,
        action="answer.version_create",
        resource_type="answer_version",
        resource_id=str(version.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        detail={"entry_id": str(entry_id), "version_number": next_num},
    )
    return _version_out(version)


async def list_versions(
    session: AsyncSession, *, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> list[VersionOut]:
    await _get_entry(session, tenant_id, entry_id)
    result = await session.execute(
        select(AnswerVersion)
        .where(AnswerVersion.entry_id == entry_id, AnswerVersion.tenant_id == tenant_id)
        .order_by(AnswerVersion.version_number.desc())
    )
    return [_version_out(v) for v in result.scalars().all()]


def _require_2fa(settings: Settings, actor: User) -> None:
    if settings.require_2fa_for_approvers and not actor.totp_enabled:
        raise ForbiddenError("Approvers must enable two-factor authentication")


async def submit_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: User,
) -> VersionOut:
    version = await _get_version(session, tenant_id, version_id)
    if version.status != STATUS_DRAFT:
        raise ValidationAppError("Only draft versions can be submitted")
    entry = await _get_entry(session, tenant_id, version.entry_id)
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_edit_office(memberships, entry.office_id, is_platform_admin=actor.is_platform_admin):
        raise ForbiddenError("Not allowed to submit for this office")
    if version.editor_id != actor.id and not actor.is_platform_admin:
        # Allow office editor who owns the draft's office to submit if they are the editor.
        raise ForbiddenError("Only the version editor can submit")

    version.status = STATUS_IN_REVIEW
    await session.flush()
    await write_audit(
        session,
        action="answer.submit",
        resource_type="answer_version",
        resource_id=str(version.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return _version_out(version)


async def approve_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: User,
    settings: Settings,
) -> VersionOut:
    _require_2fa(settings, actor)
    version = await _get_version(session, tenant_id, version_id)
    if version.status != STATUS_IN_REVIEW:
        raise ValidationAppError("Only in_review versions can be approved")
    if version.editor_id == actor.id:
        raise ForbiddenError("The editor of a version cannot approve it")

    entry = await _get_entry(session, tenant_id, version.entry_id)
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_approve_office(
        memberships, entry.office_id, is_platform_admin=actor.is_platform_admin
    ):
        raise ForbiddenError("Not allowed to approve for this office")

    version.status = STATUS_APPROVED
    version.approver_id = actor.id
    version.approved_at = datetime.now(UTC)
    await session.flush()
    await write_audit(
        session,
        action="answer.approve",
        resource_type="answer_version",
        resource_id=str(version.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return _version_out(version)


async def publish_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: User,
    settings: Settings,
) -> VersionOut:
    _require_2fa(settings, actor)
    version = await _get_version(session, tenant_id, version_id)
    if version.status != STATUS_APPROVED:
        raise ValidationAppError("Only approved versions can be published")
    if version.editor_id == actor.id:
        raise ForbiddenError("The editor of a version cannot publish it")

    entry = await _get_entry(session, tenant_id, version.entry_id)
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_approve_office(
        memberships, entry.office_id, is_platform_admin=actor.is_platform_admin
    ):
        raise ForbiddenError("Not allowed to publish for this office")

    from amakuru.modules.billing.entitlements import assert_can_publish

    already = await session.execute(
        select(AnswerVersion).where(
            AnswerVersion.entry_id == version.entry_id,
            AnswerVersion.status == STATUS_PUBLISHED,
        )
    )
    if already.scalars().first() is None:
        await assert_can_publish(session, tenant_id)

    # Unpublish other published versions of the same entry.
    others = await session.execute(
        select(AnswerVersion).where(
            AnswerVersion.entry_id == version.entry_id,
            AnswerVersion.status == STATUS_PUBLISHED,
            AnswerVersion.id != version.id,
        )
    )
    for other in others.scalars().all():
        other.status = STATUS_ARCHIVED

    version.status = STATUS_PUBLISHED
    version.published_at = datetime.now(UTC)
    if version.approver_id is None:
        version.approver_id = actor.id
        version.approved_at = version.approved_at or datetime.now(UTC)
    await session.flush()
    await write_audit(
        session,
        action="answer.publish",
        resource_type="answer_version",
        resource_id=str(version.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return _version_out(version)


async def reject_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: User,
    settings: Settings,
) -> VersionOut:
    _require_2fa(settings, actor)
    version = await _get_version(session, tenant_id, version_id)
    if version.status != STATUS_IN_REVIEW:
        raise ValidationAppError("Only in_review versions can be rejected")
    if version.editor_id == actor.id:
        raise ForbiddenError("The editor of a version cannot reject it")

    entry = await _get_entry(session, tenant_id, version.entry_id)
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=actor.id)
    if not can_approve_office(
        memberships, entry.office_id, is_platform_admin=actor.is_platform_admin
    ):
        raise ForbiddenError("Not allowed to reject for this office")

    version.status = STATUS_DRAFT
    await session.flush()
    await write_audit(
        session,
        action="answer.reject",
        resource_type="answer_version",
        resource_id=str(version.id),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
    )
    return _version_out(version)


async def list_expiring_soon(
    session: AsyncSession, *, tenant_id: uuid.UUID, within_days: int = 30
) -> list[VersionOut]:
    today = date.today()
    from datetime import timedelta

    cutoff = today + timedelta(days=within_days)
    result = await session.execute(
        select(AnswerVersion)
        .where(
            AnswerVersion.tenant_id == tenant_id,
            AnswerVersion.status == STATUS_PUBLISHED,
            AnswerVersion.valid_until.is_not(None),
            AnswerVersion.valid_until <= cutoff,
        )
        .order_by(AnswerVersion.valid_until.asc())
    )
    return [_version_out(v) for v in result.scalars().all()]


async def list_needs_answer(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[NeedsAnswerOut]:
    result = await session.execute(
        select(NeedsAnswerItem)
        .where(
            NeedsAnswerItem.tenant_id == tenant_id,
            NeedsAnswerItem.status == "open",
        )
        .order_by(NeedsAnswerItem.created_at.desc())
    )
    return [
        NeedsAnswerOut(
            id=i.id,
            question_raw=i.question_raw,
            category=i.category,
            subcategory=i.subcategory,
            language=i.language,
            office_id=i.office_id,
            status=i.status,
            created_at=i.created_at,
        )
        for i in result.scalars().all()
    ]


async def create_draft_from_mapped_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    mapped: dict[str, Any],
    actor_id: uuid.UUID,
    default_office_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID | None]:
    """Create draft entry or needs-answer item. Returns (kind, id)."""
    official = (mapped.get("official_answer") or "").strip()
    question = (mapped.get("question_raw") or "").strip()
    office_name = (mapped.get("owner_office") or "").strip()
    office_id = default_office_id

    if office_name:
        result = await session.execute(
            select(Office).where(
                Office.tenant_id == tenant_id,
                Office.name == office_name,
                Office.deleted_at.is_(None),
            )
        )
        found = result.scalar_one_or_none()
        if found:
            office_id = found.id

    if not official:
        if not question:
            return "skipped", None
        item = NeedsAnswerItem(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            office_id=office_id,
            question_raw=question,
            category=mapped.get("category") or None,
            subcategory=mapped.get("subcategory") or None,
            language=mapped.get("language") or None,
            payload=mapped,
            status="open",
        )
        session.add(item)
        await session.flush()
        return "needs_answer", item.id

    if office_id is None:
        return "skipped", None

    escalate_raw = str(mapped.get("escalate_to_human") or "").strip().lower()
    escalate = escalate_raw in {"1", "true", "yes", "y"}

    def _parse_date(value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        text = str(value).strip()[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    entry = AnswerEntry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        office_id=office_id,
        category=str(mapped.get("category") or ""),
        subcategory=str(mapped.get("subcategory") or ""),
        escalate_to_human=escalate,
        season=str(mapped.get("season") or "") or None,
        applicability={},
    )
    session.add(entry)
    await session.flush()

    version = AnswerVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entry_id=entry.id,
        version_number=1,
        answer_text=official,
        source_document=str(mapped.get("source_document") or "") or None,
        last_verified=_parse_date(mapped.get("last_verified")),
        valid_until=_parse_date(mapped.get("valid_until")),
        status=STATUS_DRAFT,
        editor_id=actor_id,
    )
    session.add(version)

    if question:
        freq = mapped.get("frequency")
        try:
            freq_int = int(str(freq)) if freq not in (None, "") else None
        except (TypeError, ValueError):
            freq_int = None
        session.add(
            QuestionVariant(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                entry_id=entry.id,
                raw_text=question,
                language=str(mapped.get("language") or "en"),
                asker_type=str(mapped.get("asker_type") or "") or None,
                channel=str(mapped.get("channel") or "") or None,
                frequency=freq_int,
                collector=str(mapped.get("collector") or "") or None,
                date_collected=_parse_date(mapped.get("date_collected")),
            )
        )
    await session.flush()
    return "entry", entry.id


# Silence unused import if Membership referenced only via deps
_ = Membership
