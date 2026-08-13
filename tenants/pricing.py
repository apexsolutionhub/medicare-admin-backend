"""Pricing catalog helpers for Medicare pharmacy tenants."""

from __future__ import annotations

from .models import SubscriptionPricingRule

PRICING_TIER_MODULES = {"Inventory", "Sales", "Reports"}


def parse_modules(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    return [str(m).strip() for m in raw if str(m).strip()]


def modules_for_pricing_lookup(modules) -> list[str]:
    return [m for m in parse_modules(modules) if m in PRICING_TIER_MODULES]


def build_modules_key(modules) -> str:
    return "|".join(sorted(set(modules_for_pricing_lookup(modules))))


def modules_from_key(modules_key: str) -> list[str]:
    if not modules_key:
        return []
    return [s.strip() for s in str(modules_key).split("|") if s.strip()]


def fallback_pricing(modules) -> dict:
    """Hardcoded Medicare matrix when no catalog rule matches."""
    set_m = set(modules_for_pricing_lookup(modules))
    has_inv = "Inventory" in set_m
    has_sales = "Sales" in set_m
    has_reports = "Reports" in set_m
    count = sum([has_inv, has_sales, has_reports])

    if count >= 3:
        return {"setup_fee_etb": 25000, "quarterly_fee_etb": 8000, "yearly_fee_etb": 28000}
    if count == 2:
        return {"setup_fee_etb": 20000, "quarterly_fee_etb": 6500, "yearly_fee_etb": 22000}
    if count == 1:
        return {"setup_fee_etb": 15000, "quarterly_fee_etb": 5000, "yearly_fee_etb": 18000}
    return {"setup_fee_etb": 15000, "quarterly_fee_etb": 5000, "yearly_fee_etb": 18000}


def resolve_pricing(business_type: str, modules) -> dict:
    bt = (business_type or "Pharmacy").strip() or "Pharmacy"
    key = build_modules_key(modules)
    row = SubscriptionPricingRule.objects.filter(
        business_type=bt, modules_key=key, is_active=True
    ).first()
    if row:
        return {
            "setup_fee_etb": row.setup_fee_etb,
            "quarterly_fee_etb": row.quarterly_fee_etb,
            "yearly_fee_etb": row.yearly_fee_etb,
            "pricing_rule_id": row.id,
            "source": "catalog",
            "modules_key": key,
        }
    fees = fallback_pricing(modules)
    return {**fees, "pricing_rule_id": None, "source": "fallback", "modules_key": key}


def write_audit(*, action: str, pharmacy_tin: str = "", actor_username: str = "", detail: str = "", metadata=None):
    from .models import ApexAuditLog

    ApexAuditLog.objects.create(
        action=action,
        pharmacy_tin=pharmacy_tin or "",
        actor_username=actor_username or "",
        detail=detail or "",
        metadata=metadata or {},
    )
