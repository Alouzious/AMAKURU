"""WhatsApp Cloud API webhook — verify, signature, dedupe, reply."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated, Any

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.logging import get_logger
from amakuru.core.security import decrypt_secret
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.channels.models import DEFAULT_QUICK_TOPICS, ChannelConfig
from amakuru.modules.channels.service import run_chat_turn
from amakuru.modules.tenancy.models import Tenant

logger = get_logger("amakuru.whatsapp")
router = APIRouter(prefix="/public/whatsapp", tags=["channels-whatsapp"])

QUICK_TOPIC_BUTTONS = [
    {"type": "reply", "reply": {"id": t["id"], "title": t["label"][:20]}}
    for t in DEFAULT_QUICK_TOPICS[:3]
]


def verify_meta_signature(
    *, app_secret: str, raw_body: bytes, signature_header: str | None
) -> bool:
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header.split("=", 1)[1]
    digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


async def _dedupe(settings: Settings, message_id: str) -> bool:
    """Return True if this message was already processed."""
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        key = f"amakuru:wa:dedupe:{message_id}"
        was_set = await client.set(key, "1", nx=True, ex=86400)
        await client.close()
        return was_set is None
    except Exception:
        return False


async def _find_tenant_by_phone_number_id(
    session: AsyncSession, phone_number_id: str
) -> tuple[Tenant, ChannelConfig] | None:
    await set_tenant(session, None)
    result = await session.execute(
        select(ChannelConfig).where(
            ChannelConfig.whatsapp_phone_number_id == phone_number_id,
            ChannelConfig.whatsapp_enabled.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        return None
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == config.tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        return None
    await set_tenant(session, tenant.id)
    return tenant, config


async def send_whatsapp_text(
    *,
    settings: Settings,
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
    buttons: list[dict[str, Any]] | None = None,
) -> None:
    version = settings.whatsapp_graph_api_version or "v21.0"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}"}
    if buttons:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text[:1024]},
                "action": {"buttons": buttons},
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning("whatsapp_send_failed", status=resp.status_code, body=resp.text[:300])


@router.get("/webhook")
async def verify_webhook(
    settings: Annotated[Settings, Depends(get_settings)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    if (
        hub_mode == "subscribe"
        and hub_verify_token
        and settings.whatsapp_verify_token
        and hmac.compare_digest(hub_verify_token, settings.whatsapp_verify_token)
    ):
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, str]:
    raw = await request.body()
    if settings.meta_app_secret:
        if not verify_meta_signature(
            app_secret=settings.meta_app_secret,
            raw_body=raw,
            signature_header=x_hub_signature_256,
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")
    elif settings.app_env == "production":
        raise HTTPException(status_code=401, detail="META_APP_SECRET required")

    try:
        payload = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    # Acknowledge quickly; process inline for Phase 4 (worker queue later)
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            if not phone_number_id:
                continue
            resolved = await _find_tenant_by_phone_number_id(session, phone_number_id)
            if resolved is None:
                logger.info("whatsapp_unknown_phone_number_id", id=phone_number_id)
                continue
            tenant, config = resolved
            token = ""
            if config.whatsapp_access_token_enc:
                try:
                    token = decrypt_secret(settings, config.whatsapp_access_token_enc)
                except Exception:
                    logger.warning("whatsapp_token_decrypt_failed", tenant=str(tenant.id))

            for msg in value.get("messages") or []:
                message_id = str(msg.get("id") or "")
                if message_id and await _dedupe(settings, message_id):
                    continue
                from_wa = str(msg.get("from") or "")
                text = ""
                if msg.get("type") == "text":
                    text = str((msg.get("text") or {}).get("body") or "")
                elif msg.get("type") == "interactive":
                    interactive = msg.get("interactive") or {}
                    if interactive.get("type") == "button_reply":
                        btn = interactive.get("button_reply") or {}
                        btn_id = str(btn.get("id") or "")
                        for topic in DEFAULT_QUICK_TOPICS:
                            if topic["id"] == btn_id:
                                text = topic["prompt"]
                                break
                        if not text:
                            text = str(btn.get("title") or "")
                if not text:
                    continue

                result = await run_chat_turn(
                    session,
                    tenant_id=tenant.id,
                    question=text,
                    language=tenant.default_language,
                    channel="whatsapp",
                    settings=settings,
                    external_thread_id=from_wa,
                )
                await session.commit()
                reply = result.get("reply") or "I am not sure how to help with that."
                buttons = None
                if result["decision"] in {"greeting", "clarify"}:
                    buttons = QUICK_TOPIC_BUTTONS
                if token and config.whatsapp_phone_number_id:
                    await send_whatsapp_text(
                        settings=settings,
                        phone_number_id=config.whatsapp_phone_number_id,
                        access_token=token,
                        to=from_wa,
                        text=reply,
                        buttons=buttons,
                    )
                else:
                    logger.info(
                        "whatsapp_reply_stubbed",
                        to=from_wa,
                        decision=result["decision"],
                        reply=reply[:120],
                    )

    return {"status": "ok"}
