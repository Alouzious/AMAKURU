"""Canonical plan catalogue. Checked in one place for entitlements."""

from __future__ import annotations

from typing import Any

PLAN_CODES = ("starter", "campus", "enterprise")

# Entitlement keys used by require_entitlement / quota checks.
ENT_MAX_PUBLISHED = "max_published_answers"
ENT_MONTHLY_CONVERSATIONS = "monthly_answered_conversations"
ENT_LANGUAGES = "languages"
ENT_WHATSAPP = "whatsapp"
ENT_API_ACCESS = "api_access"
ENT_CUSTOM_DOMAIN = "custom_domain"
ENT_WHITE_LABEL = "white_label"
ENT_SOVEREIGN = "sovereign_deployment"
ENT_SUPPORT = "support_level"

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "description": "Single campus FAQ bot — widget only, English.",
        "entitlements": {
            ENT_MAX_PUBLISHED: 100,
            ENT_MONTHLY_CONVERSATIONS: 2_000,
            ENT_LANGUAGES: ["en"],
            ENT_WHATSAPP: False,
            ENT_API_ACCESS: False,
            ENT_CUSTOM_DOMAIN: False,
            ENT_WHITE_LABEL: False,
            ENT_SOVEREIGN: False,
            ENT_SUPPORT: "community",
        },
    },
    "campus": {
        "name": "Campus",
        "description": "Multi-language campus with WhatsApp and API access.",
        "entitlements": {
            ENT_MAX_PUBLISHED: 1_000,
            ENT_MONTHLY_CONVERSATIONS: 25_000,
            ENT_LANGUAGES: ["en", "lg", "nyn", "sw"],
            ENT_WHATSAPP: True,
            ENT_API_ACCESS: True,
            ENT_CUSTOM_DOMAIN: False,
            ENT_WHITE_LABEL: False,
            ENT_SOVEREIGN: False,
            ENT_SUPPORT: "standard",
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "description": "White-label, sovereign option, high volume.",
        "entitlements": {
            ENT_MAX_PUBLISHED: 10_000,
            ENT_MONTHLY_CONVERSATIONS: 500_000,
            ENT_LANGUAGES: ["en", "lg", "nyn", "sw", "ach", "teo", "lgg"],
            ENT_WHATSAPP: True,
            ENT_API_ACCESS: True,
            ENT_CUSTOM_DOMAIN: True,
            ENT_WHITE_LABEL: True,
            ENT_SOVEREIGN: True,
            ENT_SUPPORT: "priority",
        },
    },
}


def entitlements_for(plan: str) -> dict[str, Any]:
    code = plan if plan in PLAN_CATALOG else "starter"
    return dict(PLAN_CATALOG[code]["entitlements"])


def plan_summary(plan: str) -> dict[str, Any]:
    code = plan if plan in PLAN_CATALOG else "starter"
    meta = PLAN_CATALOG[code]
    return {
        "code": code,
        "name": meta["name"],
        "description": meta["description"],
        "entitlements": entitlements_for(code),
    }
