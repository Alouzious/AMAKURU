"""FastAPI dependencies for auth."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db
from amakuru.core.errors import AuthError, ForbiddenError
from amakuru.core.security import parse_uuid
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.identity import service as identity_service
from amakuru.modules.identity.models import User
from amakuru.modules.identity.schemas import UserOut

SESSION_COOKIE = "amakuru_session"
REFRESH_COOKIE = "amakuru_refresh"
CSRF_HEADER = "X-CSRF-Token"

CurrentAuth = tuple[User, UserOut, UUID]


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> CurrentAuth:
    if not session_cookie:
        raise AuthError("Not authenticated")
    session_id = parse_uuid(session_cookie)
    if session_id is None:
        raise AuthError("Not authenticated")

    sess = await identity_service.get_valid_session(session, session_id)
    if sess is None:
        raise AuthError("Not authenticated")

    if sess.expires_at < datetime.now(UTC):
        raise AuthError("Session expired; refresh required")

    user = await identity_service.get_user_by_id(session, sess.user_id)
    if user is None or not user.is_active:
        raise AuthError("Not authenticated")

    user_out = await identity_service.build_user_out(session, user, csrf=sess.csrf_token)
    request.state.csrf_token = sess.csrf_token
    return user, user_out, sess.id


async def require_csrf(
    request: Request,
    auth: Annotated[CurrentAuth, Depends(get_current_user)],
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> CurrentAuth:
    user, user_out, session_id = auth
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return user, user_out, session_id
    expected = user_out.csrf_token
    if not csrf_header or not expected or csrf_header != expected:
        raise ForbiddenError("CSRF token missing or invalid")
    return user, user_out, session_id


def get_settings_dep() -> Settings:
    return get_settings()
