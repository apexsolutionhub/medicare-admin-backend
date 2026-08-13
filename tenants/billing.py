"""
Billing helpers for pharmacy-admin (mirrors pharmacy.tenants.billing logic).
Kept local so admin does not import the pharmacy package.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import TenantAccount, TenantPaymentSubmission

PERIOD_DAYS = 90


def compute_subscription_paid_until(*, started_at, periods: int):
    if not started_at or periods <= 0:
        return None
    return started_at + timedelta(days=PERIOD_DAYS * periods)


def approve_setup_payment(*, tenant: TenantAccount, approved_by=None) -> TenantAccount:
    now = timezone.now()
    pending = (
        TenantPaymentSubmission.objects.filter(
            pharmacy_tin=tenant.pharmacy_tin,
            payment_kind=TenantPaymentSubmission.KIND_SETUP,
            status=TenantPaymentSubmission.STATUS_PENDING,
        )
        .order_by("-submitted_at")
        .first()
    )
    if pending:
        pending.status = TenantPaymentSubmission.STATUS_APPROVED
        pending.approved_at = now
        pending.approved_by = approved_by
        pending.save(update_fields=["status", "approved_at", "approved_by"])

    billing_applies = int(tenant.quarterly_fee_etb or 0) > 0
    tenant.setup_fee_approved = True
    tenant.subscription_payment_approved = billing_applies
    tenant.paid_quarters_count = 1 if billing_applies else 0
    tenant.billing_started_at = now if billing_applies else None
    tenant.subscription_paid_until = (
        compute_subscription_paid_until(started_at=now, periods=1) if billing_applies else None
    )
    tenant.save()
    return tenant


def approve_quarterly_payment(*, tenant: TenantAccount, approved_by=None) -> TenantAccount:
    if int(tenant.quarterly_fee_etb or 0) <= 0:
        raise ValueError("Quarterly billing is not enabled for this tenant.")

    now = timezone.now()
    pending = (
        TenantPaymentSubmission.objects.filter(
            pharmacy_tin=tenant.pharmacy_tin,
            payment_kind=TenantPaymentSubmission.KIND_QUARTERLY,
            status=TenantPaymentSubmission.STATUS_PENDING,
        )
        .order_by("-submitted_at")
        .first()
    )
    if pending:
        pending.status = TenantPaymentSubmission.STATUS_APPROVED
        pending.approved_at = now
        pending.approved_by = approved_by
        pending.save(update_fields=["status", "approved_at", "approved_by"])

    next_periods = int(tenant.paid_quarters_count or 0) + 1
    started = tenant.billing_started_at or tenant.created_at or now
    if not tenant.billing_started_at:
        tenant.billing_started_at = started

    tenant.subscription_payment_approved = True
    tenant.paid_quarters_count = next_periods
    tenant.subscription_paid_until = compute_subscription_paid_until(
        started_at=started,
        periods=next_periods,
    )
    tenant.save()
    return tenant


def reject_payment_submission(*, submission: TenantPaymentSubmission, reason: str, rejected_by=None):
    submission.status = TenantPaymentSubmission.STATUS_REJECTED
    submission.rejection_reason = (reason or "").strip()
    submission.rejected_at = timezone.now()
    submission.rejected_by = rejected_by
    submission.save()
    return submission


def approve_yearly_payment(*, tenant: TenantAccount, approved_by=None) -> TenantAccount:
    """Approve yearly renewal — extends coverage by 4 quarters (≈365 days of periods)."""
    if int(getattr(tenant, "yearly_fee_etb", 0) or 0) <= 0 and int(tenant.quarterly_fee_etb or 0) <= 0:
        raise ValueError("Yearly billing is not enabled for this tenant.")

    now = timezone.now()
    pending = (
        TenantPaymentSubmission.objects.filter(
            pharmacy_tin=tenant.pharmacy_tin,
            payment_kind=TenantPaymentSubmission.KIND_YEARLY,
            status=TenantPaymentSubmission.STATUS_PENDING,
        )
        .order_by("-submitted_at")
        .first()
    )
    if pending:
        pending.status = TenantPaymentSubmission.STATUS_APPROVED
        pending.approved_at = now
        pending.approved_by = approved_by
        pending.save(update_fields=["status", "approved_at", "approved_by"])

    next_periods = int(tenant.paid_quarters_count or 0) + 4
    started = tenant.billing_started_at or tenant.created_at or now
    if not tenant.billing_started_at:
        tenant.billing_started_at = started

    tenant.subscription_payment_approved = True
    tenant.paid_quarters_count = next_periods
    tenant.subscription_paid_until = compute_subscription_paid_until(
        started_at=started,
        periods=next_periods,
    )
    tenant.save()
    return tenant


def release_billing_hold(*, tenant: TenantAccount) -> TenantAccount:
    now = timezone.now()
    billing_applies = int(tenant.quarterly_fee_etb or 0) > 0
    tenant.billing_hold = False
    tenant.billing_started_at = now
    if billing_applies and tenant.setup_fee_approved:
        tenant.paid_quarters_count = max(int(tenant.paid_quarters_count or 0), 1)
        tenant.subscription_payment_approved = True
        tenant.subscription_paid_until = compute_subscription_paid_until(
            started_at=now,
            periods=tenant.paid_quarters_count,
        )
    tenant.save()
    return tenant
