"""REST API v1: mounts every domain router under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from amakuru.modules.analytics.router import router as analytics_router
from amakuru.modules.billing.router import external_router as billing_external_router
from amakuru.modules.billing.router import router as billing_router
from amakuru.modules.channels.router import router as channels_public_router
from amakuru.modules.channels.whatsapp import router as whatsapp_router
from amakuru.modules.identity.router import router as identity_router
from amakuru.modules.knowledge.router import router as knowledge_router
from amakuru.modules.retrieval.router import router as retrieval_router
from amakuru.modules.tenancy.router import router as tenancy_router

api_v1 = APIRouter(prefix="/api/v1")

# Auth
api_v1.include_router(identity_router)

# Tenants and offices
api_v1.include_router(tenancy_router)

# Answer bank / governance
api_v1.include_router(knowledge_router)

# Ask / retrieval
api_v1.include_router(retrieval_router)

# Dashboard analytics
api_v1.include_router(analytics_router)

# Plans, usage, API keys, onboarding
api_v1.include_router(billing_router)
api_v1.include_router(billing_external_router)

# Public widget chat + WhatsApp webhooks
api_v1.include_router(channels_public_router)
api_v1.include_router(whatsapp_router)
