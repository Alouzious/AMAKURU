"""Plan catalogue and entitlement helpers."""

from __future__ import annotations

from amakuru.modules.billing.catalog import PLAN_CATALOG, entitlements_for, plan_summary


def test_three_plans_defined() -> None:
    assert set(PLAN_CATALOG) == {"starter", "campus", "enterprise"}


def test_starter_lacks_api_and_whatsapp() -> None:
    ents = entitlements_for("starter")
    assert ents["api_access"] is False
    assert ents["whatsapp"] is False
    assert ents["white_label"] is False


def test_campus_has_api() -> None:
    ents = entitlements_for("campus")
    assert ents["api_access"] is True
    assert "lg" in ents["languages"]


def test_unknown_plan_falls_back_to_starter() -> None:
    assert plan_summary("nope")["code"] == "starter"
