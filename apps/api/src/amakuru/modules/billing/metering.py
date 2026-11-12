"""Usage metering — increments daily aggregates per tenant."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.billing.models import UsageEvent

EVENT_ANSWERED = "answered_conversation"
EVENT_TOKENS = "tokens"
EVENT_WHATSAPP = "whatsapp_message"
EVENT_COST = "estimated_cost_usd"


async def _bump(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    event_type: str,
    quantity: int = 1,
    cost: Decimal | float = 0,
    day: date | None = None,
) -> None:
    d = day or datetime.now(UTC).date()
    result = await session.execute(
        select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.day == d,
            UsageEvent.event_type == event_type,
        )
    )
    row = result.scalar_one_or_none()
    cost_dec = Decimal(str(cost))
    if row is None:
        session.add(
            UsageEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                day=d,
                event_type=event_type,
                quantity=quantity,
                estimated_cost_usd=cost_dec,
                meta={},
            )
        )
    else:
        row.quantity = int(row.quantity) + quantity
        row.estimated_cost_usd = Decimal(str(row.estimated_cost_usd)) + cost_dec
    await session.flush()


async def record_answered_turn(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    channel: str = "widget",
) -> None:
    await _bump(
        session,
        tenant_id=tenant_id,
        event_type=EVENT_ANSWERED,
        quantity=1,
        cost=estimated_cost_usd,
    )
    if tokens:
        await _bump(session, tenant_id=tenant_id, event_type=EVENT_TOKENS, quantity=tokens)
    if channel == "whatsapp":
        await _bump(session, tenant_id=tenant_id, event_type=EVENT_WHATSAPP, quantity=1)


async def list_usage(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    from_day: date,
    to_day: date,
) -> list[UsageEvent]:
    result = await session.execute(
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.day >= from_day,
            UsageEvent.day <= to_day,
        )
        .order_by(UsageEvent.day.asc(), UsageEvent.event_type.asc())
    )
    return list(result.scalars().all())
