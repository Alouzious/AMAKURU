"""Auth HTTP routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db
from amakuru.core.errors import ValidationAppError
from amakuru.core.settings import Settings
from amakuru.modules.identity import service as identity_service
from amakuru.modules.identity import totp as totp_service
from amakuru.modules.identity.deps import (
    REFRESH_COOKIE,
    SESSION_COOKIE,
    CurrentAuth,
    get_current_user,
    get_settings_dep,
    require_csrf,
)
from amakuru.modules.identity.schemas import (
    LoginRequest,
    LoginResponse,
    MessageOut,
    TotpSetupOut,
    TotpVerifyRequest,
    UserOut,
)
from amakuru.modules.platform.audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    session_id: str,
    refresh_token: str,
) -> None:
    secure = settings.app_env == "production"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.refresh_ttl_days * 24 * 3600,
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LoginResponse:
    user_out, session_id, refresh = await identity_service.login(
        session,
        settings,
        email=body.email,
        password=body.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    _set_auth_cookies(response, settings, session_id=session_id, refresh_token=refresh)
    return LoginResponse(user=user_out)


@router.post("/logout", response_model=MessageOut)
async def logout(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[CurrentAuth, Depends(require_csrf)],
) -> MessageOut:
    user, _user_out, session_id = auth
    await identity_service.logout(session, session_id=session_id, user_id=user.id)
    await session.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Logged out")


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LoginResponse:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    refresh_cookie = request.cookies.get(REFRESH_COOKIE)
    if not session_cookie or not refresh_cookie:
        from amakuru.core.errors import AuthError

        raise AuthError("Missing session")
    session_id = UUID(session_cookie)
    user_out, new_session_id, new_refresh = await identity_service.refresh_session(
        session,
        settings,
        session_id=session_id,
        refresh_token=refresh_cookie,
    )
    await session.commit()
    _set_auth_cookies(response, settings, session_id=new_session_id, refresh_token=new_refresh)
    return LoginResponse(user=user_out, message="Session refreshed")


@router.get("/me", response_model=UserOut)
async def me(auth: Annotated[CurrentAuth, Depends(get_current_user)]) -> UserOut:
    _user, user_out, _sid = auth
    return user_out


@router.post("/2fa/setup", response_model=TotpSetupOut)
async def totp_setup(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    auth: Annotated[CurrentAuth, Depends(require_csrf)],
) -> TotpSetupOut:
    user, _user_out, _sid = auth
    payload = totp_service.setup_payload(settings, user)
    await write_audit(
        session,
        action="auth.2fa_setup",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    await session.commit()
    return TotpSetupOut(**payload)


@router.post("/2fa/verify", response_model=MessageOut)
async def totp_verify(
    body: TotpVerifyRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    auth: Annotated[CurrentAuth, Depends(require_csrf)],
) -> MessageOut:
    user, _user_out, _sid = auth
    if not totp_service.enable_totp(settings, user, body.code):
        raise ValidationAppError("Invalid authentication code")
    await write_audit(
        session,
        action="auth.2fa_enabled",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    await session.commit()
    return MessageOut(message="Two-factor authentication enabled")
