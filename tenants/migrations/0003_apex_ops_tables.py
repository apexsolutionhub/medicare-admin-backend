# Generated manually for Medicare Apex ops tables

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenantpaymentsubmission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPricingRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("business_type", models.CharField(db_index=True, max_length=64)),
                ("modules_key", models.CharField(db_index=True, max_length=255)),
                ("modules", models.JSONField(blank=True, default=list)),
                ("setup_fee_etb", models.PositiveIntegerField(default=15000)),
                ("quarterly_fee_etb", models.PositiveIntegerField(default=5000)),
                ("yearly_fee_etb", models.PositiveIntegerField(default=18000)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "tenants_subscriptionpricingrule",
                "ordering": ["sort_order", "business_type", "modules_key"],
                "unique_together": {("business_type", "modules_key")},
            },
        ),
        migrations.CreateModel(
            name="TenantModuleChangeRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pharmacy_tin", models.CharField(db_index=True, max_length=50)),
                ("requested_modules", models.JSONField(default=list)),
                ("request_note", models.TextField(blank=True, default="")),
                ("status", models.CharField(db_index=True, default="pending", max_length=20)),
                ("requested_by_side", models.CharField(default="tenant", max_length=20)),
                ("requested_by_username", models.CharField(blank=True, default="", max_length=150)),
                ("review_note", models.TextField(blank=True, default="")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("setup_fee_snapshot", models.PositiveIntegerField(blank=True, null=True)),
                ("quarterly_fee_snapshot", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "tenants_tenantmodulechangerequest",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TenantFeedbackThread",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pharmacy_tin", models.CharField(db_index=True, max_length=50, unique=True)),
                ("status", models.CharField(db_index=True, default="open", max_length=20)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "closed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "tenants_tenantfeedbackthread",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="TenantFeedbackMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_side", models.CharField(max_length=20)),
                ("body", models.TextField()),
                ("image_url", models.URLField(blank=True, default="")),
                ("sender_username", models.CharField(blank=True, default="", max_length=150)),
                ("read_by_tenant", models.BooleanField(default=False)),
                ("read_by_apex", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="tenants.tenantfeedbackthread",
                    ),
                ),
            ],
            options={
                "db_table": "tenants_tenantfeedbackmessage",
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="ApexAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("pharmacy_tin", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("actor_username", models.CharField(blank=True, default="", max_length=150)),
                ("detail", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "tenants_apexauditlog",
                "ordering": ["-created_at"],
            },
        ),
    ]
