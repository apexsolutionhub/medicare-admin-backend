from django.conf import settings
from django.db import models


class TenantAccount(models.Model):
    """Mirrors pharmacy.tenants.TenantAccount (shared MySQL table)."""

    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_BANNED = "banned"
    STATUS_DELETED = "deleted"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_BANNED, "Banned"),
        (STATUS_DELETED, "Deleted"),
    ]

    pharmacy_tin = models.CharField(max_length=50, unique=True, db_index=True)
    pharmacy_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")
    account_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )
    status_reason = models.TextField(blank=True, default="")
    status_changed_at = models.DateTimeField(null=True, blank=True)

    setup_fee_etb = models.PositiveIntegerField(default=15000)
    quarterly_fee_etb = models.PositiveIntegerField(default=5000)
    yearly_fee_etb = models.PositiveIntegerField(default=18000)
    payment_channel = models.CharField(max_length=64, blank=True, default="")
    payment_transaction_ref = models.CharField(max_length=128, blank=True, default="")
    setup_fee_approved = models.BooleanField(default=False)
    subscription_payment_approved = models.BooleanField(default=False)
    subscription_paid_until = models.DateTimeField(null=True, blank=True)
    paid_quarters_count = models.PositiveIntegerField(default=0)
    billing_hold = models.BooleanField(default=False)
    billing_started_at = models.DateTimeField(null=True, blank=True)
    free_trial_ends_at = models.DateTimeField(null=True, blank=True)
    is_illustration = models.BooleanField(default=False)
    billing_notes = models.TextField(blank=True, default="")
    modules = models.JSONField(default=list, blank=True)
    fees_manually_set = models.BooleanField(default=False)
    sales_agent = models.ForeignKey(
        "SalesAgent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenants",
        db_constraint=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "tenants_tenantaccount"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pharmacy_name or self.pharmacy_tin} ({self.account_status})"


class TenantPaymentSubmission(models.Model):
    KIND_SETUP = "setup"
    KIND_QUARTERLY = "quarterly"
    KIND_YEARLY = "yearly"
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    pharmacy_tin = models.CharField(max_length=50, db_index=True)
    payment_kind = models.CharField(max_length=20, db_index=True)
    amount_etb = models.PositiveIntegerField()
    payment_channel = models.CharField(max_length=64)
    transaction_ref = models.CharField(max_length=128)
    status = models.CharField(max_length=20, default=STATUS_PENDING, db_index=True)
    submitted_at = models.DateTimeField()
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
    )
    rejection_reason = models.TextField(blank=True, default="")
    quarter_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "tenants_tenantpaymentsubmission"
        ordering = ["-submitted_at"]


class UserProfile(models.Model):
    """Mirrors pharmacy.user.UserProfile (shared MySQL table)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pharmacy_profile",
    )
    pharmacy_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=100, blank=True)
    logoUrl = models.URLField(blank=True)
    pharmacy_tin = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "user_userprofile"

    def __str__(self):
        return self.user.username


class SubscriptionPricingRule(models.Model):
    business_type = models.CharField(max_length=64, db_index=True)
    modules_key = models.CharField(max_length=255, db_index=True)
    modules = models.JSONField(default=list, blank=True)
    setup_fee_etb = models.PositiveIntegerField(default=15000)
    quarterly_fee_etb = models.PositiveIntegerField(default=5000)
    yearly_fee_etb = models.PositiveIntegerField(default=18000)
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_subscriptionpricingrule"
        ordering = ["sort_order", "business_type", "modules_key"]
        unique_together = [("business_type", "modules_key")]

    def __str__(self):
        return f"{self.business_type} [{self.modules_key}]"


class TenantModuleChangeRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"

    pharmacy_tin = models.CharField(max_length=50, db_index=True)
    requested_modules = models.JSONField(default=list)
    request_note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, default=STATUS_PENDING, db_index=True)
    requested_by_side = models.CharField(max_length=20, default="tenant")
    requested_by_username = models.CharField(max_length=150, blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    review_note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    setup_fee_snapshot = models.PositiveIntegerField(null=True, blank=True)
    quarterly_fee_snapshot = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenantmodulechangerequest"
        ordering = ["-created_at"]


class TenantFeedbackThread(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"

    pharmacy_tin = models.CharField(max_length=50, unique=True, db_index=True)
    status = models.CharField(max_length=20, default=STATUS_OPEN, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenantfeedbackthread"
        ordering = ["-updated_at"]


class TenantFeedbackMessage(models.Model):
    SIDE_TENANT = "tenant"
    SIDE_APEX = "apex"

    thread = models.ForeignKey(
        TenantFeedbackThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_side = models.CharField(max_length=20)
    body = models.TextField()
    image_url = models.URLField(blank=True, default="")
    sender_username = models.CharField(max_length=150, blank=True, default="")
    read_by_tenant = models.BooleanField(default=False)
    read_by_apex = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants_tenantfeedbackmessage"
        ordering = ["created_at"]


class ApexAuditLog(models.Model):
    action = models.CharField(max_length=64, db_index=True)
    pharmacy_tin = models.CharField(max_length=50, blank=True, default="", db_index=True)
    actor_username = models.CharField(max_length=150, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants_apexauditlog"
        ordering = ["-created_at"]


class SalesAgent(models.Model):
    display_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "tenants_salesagent"
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name
