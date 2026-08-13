from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .billing import (
    approve_quarterly_payment,
    approve_setup_payment,
    approve_yearly_payment,
    reject_payment_submission,
    release_billing_hold,
)
from .models import TenantAccount, TenantPaymentSubmission, UserProfile
from .pricing import write_audit

User = get_user_model()

DEFAULT_SETUP_FEE_ETB = 15000
DEFAULT_QUARTERLY_FEE_ETB = 5000
DEFAULT_YEARLY_FEE_ETB = 18000
DEFAULT_MODULES = ["Inventory", "Sales", "Reports"]


class TenantSerializer(serializers.ModelSerializer):
    manager_count = serializers.IntegerField(read_only=True, required=False)
    pharmacist_count = serializers.IntegerField(read_only=True, required=False)
    staff_count = serializers.IntegerField(read_only=True, required=False)
    manager_username = serializers.CharField(read_only=True, required=False, default="")

    class Meta:
        model = TenantAccount
        fields = [
            "id",
            "pharmacy_tin",
            "pharmacy_name",
            "phone",
            "logo_url",
            "account_status",
            "status_reason",
            "status_changed_at",
            "setup_fee_etb",
            "quarterly_fee_etb",
            "yearly_fee_etb",
            "payment_channel",
            "payment_transaction_ref",
            "setup_fee_approved",
            "subscription_payment_approved",
            "subscription_paid_until",
            "paid_quarters_count",
            "billing_hold",
            "billing_started_at",
            "free_trial_ends_at",
            "is_illustration",
            "billing_notes",
            "modules",
            "fees_manually_set",
            "created_at",
            "updated_at",
            "manager_count",
            "pharmacist_count",
            "staff_count",
            "manager_username",
        ]
        read_only_fields = [
            "id",
            "account_status",
            "status_reason",
            "status_changed_at",
            "payment_channel",
            "payment_transaction_ref",
            "setup_fee_approved",
            "subscription_payment_approved",
            "subscription_paid_until",
            "paid_quarters_count",
            "billing_started_at",
            "created_at",
            "updated_at",
            "manager_count",
            "pharmacist_count",
            "staff_count",
            "manager_username",
        ]


class PaymentSubmissionSerializer(serializers.ModelSerializer):
    pharmacy_name = serializers.SerializerMethodField()

    class Meta:
        model = TenantPaymentSubmission
        fields = [
            "id",
            "pharmacy_tin",
            "pharmacy_name",
            "payment_kind",
            "amount_etb",
            "payment_channel",
            "transaction_ref",
            "status",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "rejection_reason",
            "quarter_number",
        ]

    def get_pharmacy_name(self, obj):
        tenant = TenantAccount.objects.filter(pharmacy_tin=obj.pharmacy_tin).first()
        return tenant.pharmacy_name if tenant else ""


class TenantCreateSerializer(serializers.Serializer):
    pharmacy_tin = serializers.CharField(max_length=50)
    pharmacy_name = serializers.CharField(max_length=255)
    logo_url = serializers.URLField(required=False, allow_blank=True, default="")
    manager_username = serializers.CharField(max_length=150)
    manager_password = serializers.CharField(write_only=True, min_length=6)
    setup_fee_etb = serializers.IntegerField(required=False, min_value=0, default=DEFAULT_SETUP_FEE_ETB)
    quarterly_fee_etb = serializers.IntegerField(
        required=False, min_value=0, default=DEFAULT_QUARTERLY_FEE_ETB
    )
    yearly_fee_etb = serializers.IntegerField(
        required=False, min_value=0, default=DEFAULT_YEARLY_FEE_ETB
    )
    modules = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=DEFAULT_MODULES,
    )
    waive_setup_fee = serializers.BooleanField(required=False, default=False)

    def validate_pharmacy_tin(self, value):
        tin = (value or "").strip()
        if not tin:
            raise serializers.ValidationError("Pharmacy TIN is required.")
        if TenantAccount.objects.filter(pharmacy_tin=tin).exists():
            raise serializers.ValidationError("A tenant with this TIN already exists.")
        if UserProfile.objects.filter(pharmacy_tin=tin).exists():
            raise serializers.ValidationError("This TIN is already used by pharmacy users.")
        return tin

    def validate_manager_username(self, value):
        username = (value or "").strip()
        if not username:
            raise serializers.ValidationError("Manager username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("This username is already taken.")
        return username

    @transaction.atomic
    def create(self, validated_data):
        tin = validated_data["pharmacy_tin"]
        pharmacy_name = validated_data["pharmacy_name"].strip()
        logo_url = (validated_data.get("logo_url") or "").strip()
        setup_fee = int(validated_data.get("setup_fee_etb", DEFAULT_SETUP_FEE_ETB))
        quarterly_fee = int(validated_data.get("quarterly_fee_etb", DEFAULT_QUARTERLY_FEE_ETB))
        yearly_fee = int(validated_data.get("yearly_fee_etb", DEFAULT_YEARLY_FEE_ETB))
        modules = validated_data.get("modules") or list(DEFAULT_MODULES)
        waive = bool(validated_data.get("waive_setup_fee"))

        user = User(username=validated_data["manager_username"])
        user.set_password(validated_data["manager_password"])
        user.save()

        UserProfile.objects.create(
            user=user,
            pharmacy_name=pharmacy_name,
            role="Manager",
            logoUrl=logo_url,
            pharmacy_tin=tin,
        )

        now = timezone.now()
        tenant = TenantAccount.objects.create(
            pharmacy_tin=tin,
            pharmacy_name=pharmacy_name,
            logo_url=logo_url,
            account_status=TenantAccount.STATUS_ACTIVE,
            setup_fee_etb=setup_fee,
            quarterly_fee_etb=quarterly_fee,
            yearly_fee_etb=yearly_fee,
            modules=modules,
            setup_fee_approved=waive or setup_fee <= 0,
            subscription_payment_approved=(waive or setup_fee <= 0) and quarterly_fee > 0,
            paid_quarters_count=1 if ((waive or setup_fee <= 0) and quarterly_fee > 0) else 0,
            billing_started_at=now if ((waive or setup_fee <= 0) and quarterly_fee > 0) else None,
            subscription_paid_until=(
                now + timedelta(days=90)
                if ((waive or setup_fee <= 0) and quarterly_fee > 0)
                else None
            ),
            free_trial_ends_at=(
                None
                if (waive or setup_fee <= 0)
                else now + timedelta(days=14)
            ),
        )
        return tenant


class TenantUpdateSerializer(serializers.Serializer):
    pharmacy_name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    logo_url = serializers.URLField(required=False, allow_blank=True)
    setup_fee_etb = serializers.IntegerField(required=False, min_value=0)
    quarterly_fee_etb = serializers.IntegerField(required=False, min_value=0)
    yearly_fee_etb = serializers.IntegerField(required=False, min_value=0)
    fees_manually_set = serializers.BooleanField(required=False)
    modules = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False
    )
    billing_hold = serializers.BooleanField(required=False)
    billing_notes = serializers.CharField(required=False, allow_blank=True)
    is_illustration = serializers.BooleanField(required=False)
    free_trial_ends_at = serializers.DateTimeField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        for field in (
            "pharmacy_name",
            "phone",
            "logo_url",
            "setup_fee_etb",
            "quarterly_fee_etb",
            "yearly_fee_etb",
            "fees_manually_set",
            "modules",
            "billing_hold",
            "billing_notes",
            "is_illustration",
            "free_trial_ends_at",
        ):
            if field in validated_data:
                value = validated_data[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(instance, field, value)
        if any(
            f in validated_data
            for f in ("setup_fee_etb", "quarterly_fee_etb", "yearly_fee_etb")
        ):
            instance.fees_manually_set = True
        instance.save()

        UserProfile.objects.filter(pharmacy_tin=instance.pharmacy_tin).update(
            pharmacy_name=instance.pharmacy_name,
            logoUrl=instance.logo_url,
        )
        return instance


def annotate_staff_counts(queryset):
    tenants = list(queryset)
    tins = [t.pharmacy_tin for t in tenants]
    profiles = UserProfile.objects.filter(pharmacy_tin__in=tins).select_related("user")
    by_tin: dict[str, dict[str, int]] = {}
    managers_by_tin: dict[str, str] = {}
    for profile in profiles:
        tin = profile.pharmacy_tin
        role = (profile.role or "").strip().lower()
        bucket = by_tin.setdefault(tin, {"manager": 0, "pharmacist": 0, "staff": 0})
        bucket["staff"] += 1
        if role == "manager":
            bucket["manager"] += 1
            if tin not in managers_by_tin:
                managers_by_tin[tin] = profile.user.username
        elif role == "pharmacist":
            bucket["pharmacist"] += 1

    for tenant in tenants:
        counts = by_tin.get(tenant.pharmacy_tin, {"manager": 0, "pharmacist": 0, "staff": 0})
        tenant.manager_count = counts["manager"]
        tenant.pharmacist_count = counts["pharmacist"]
        tenant.staff_count = counts["staff"]
        tenant.manager_username = managers_by_tin.get(tenant.pharmacy_tin, "")
    return tenants


class TenantListCreateView(APIView):
    def get(self, request):
        qs = TenantAccount.objects.all()
        search = (request.query_params.get("search") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip().lower()

        if search:
            qs = qs.filter(
                Q(pharmacy_tin__icontains=search) | Q(pharmacy_name__icontains=search)
            )
        if status_filter:
            qs = qs.filter(account_status=status_filter)

        qs = qs.order_by("-created_at")
        tenants = annotate_staff_counts(qs)
        return Response(TenantSerializer(tenants, many=True).data)

    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        write_audit(
            action="create_tenant",
            pharmacy_tin=tenant.pharmacy_tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail=tenant.pharmacy_name or tenant.pharmacy_tin,
        )
        tenants = annotate_staff_counts(TenantAccount.objects.filter(pk=tenant.pk))
        return Response(TenantSerializer(tenants[0]).data, status=status.HTTP_201_CREATED)


class TenantDetailView(APIView):
    def get_object(self, tin: str):
        try:
            return TenantAccount.objects.get(pharmacy_tin=tin)
        except TenantAccount.DoesNotExist:
            return None

    def get(self, request, tin):
        tenant = self.get_object(tin)
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)

        tenants = annotate_staff_counts([tenant])
        staff = (
            UserProfile.objects.filter(pharmacy_tin=tin)
            .select_related("user")
            .order_by("role", "user__username")
        )
        staff_payload = [
            {
                "id": p.user_id,
                "username": p.user.username,
                "role": p.role,
                "pharmacy_name": p.pharmacy_name,
                "logoUrl": p.logoUrl,
                "pharmacy_tin": p.pharmacy_tin,
                "login_disabled": not p.user.is_active,
            }
            for p in staff
        ]
        payments = TenantPaymentSubmission.objects.filter(pharmacy_tin=tin).order_by("-submitted_at")[:20]
        data = TenantSerializer(tenants[0]).data
        data["staff"] = staff_payload
        data["payments"] = PaymentSubmissionSerializer(payments, many=True).data
        return Response(data)

    def patch(self, request, tin):
        tenant = self.get_object(tin)
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TenantUpdateSerializer(tenant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        write_audit(
            action="update_tenant_billing",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail="Updated pharmacy billing/profile settings",
            metadata={
                key: request.data.get(key)
                for key in (
                    "setup_fee_etb",
                    "quarterly_fee_etb",
                    "billing_hold",
                    "is_illustration",
                    "free_trial_ends_at",
                    "billing_notes",
                )
                if key in request.data
            },
        )
        tenants = annotate_staff_counts([tenant])
        return Response(TenantSerializer(tenants[0]).data)


class TenantStatusView(APIView):
    ACTION_MAP = {
        "suspend": TenantAccount.STATUS_SUSPENDED,
        "unsuspend": TenantAccount.STATUS_ACTIVE,
        "ban": TenantAccount.STATUS_BANNED,
        "unban": TenantAccount.STATUS_ACTIVE,
        "delete": TenantAccount.STATUS_DELETED,
        "restore": TenantAccount.STATUS_ACTIVE,
    }

    def post(self, request, tin, action):
        try:
            tenant = TenantAccount.objects.get(pharmacy_tin=tin)
        except TenantAccount.DoesNotExist:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = self.ACTION_MAP.get(action)
        if not new_status:
            return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get("reason") or "").strip()
        tenant.account_status = new_status
        tenant.status_reason = reason
        tenant.status_changed_at = timezone.now()
        tenant.save(
            update_fields=["account_status", "status_reason", "status_changed_at", "updated_at"]
        )
        write_audit(
            action=f"{action}_tenant",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail=reason or f"Marked {new_status}",
            metadata={"account_status": new_status},
        )
        tenants = annotate_staff_counts([tenant])
        return Response(TenantSerializer(tenants[0]).data)


class PendingPaymentsView(APIView):
    def get(self, request):
        kind = (request.query_params.get("kind") or "").strip().lower()
        qs = TenantPaymentSubmission.objects.filter(
            status=TenantPaymentSubmission.STATUS_PENDING
        ).order_by("submitted_at")
        if kind in {
            TenantPaymentSubmission.KIND_SETUP,
            TenantPaymentSubmission.KIND_QUARTERLY,
            TenantPaymentSubmission.KIND_YEARLY,
        }:
            qs = qs.filter(payment_kind=kind)
        return Response(PaymentSubmissionSerializer(qs, many=True).data)


class ApproveSetupPaymentView(APIView):
    def post(self, request):
        tin = (request.data.get("pharmacy_tin") or "").strip()
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        tenant = approve_setup_payment(tenant=tenant, approved_by=request.user.user)
        write_audit(
            action="approve_setup_payment",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail="Approved setup payment",
        )
        return Response(TenantSerializer(annotate_staff_counts([tenant])[0]).data)


class ApproveQuarterlyPaymentView(APIView):
    def post(self, request):
        tin = (request.data.get("pharmacy_tin") or "").strip()
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            tenant = approve_quarterly_payment(tenant=tenant, approved_by=request.user.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        write_audit(
            action="approve_quarterly_payment",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail="Approved quarterly payment",
        )
        return Response(TenantSerializer(annotate_staff_counts([tenant])[0]).data)


class ApproveYearlyPaymentView(APIView):
    def post(self, request):
        tin = (request.data.get("pharmacy_tin") or "").strip()
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            tenant = approve_yearly_payment(tenant=tenant, approved_by=request.user.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        write_audit(
            action="approve_yearly_payment",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail="Approved yearly payment",
        )
        return Response(TenantSerializer(annotate_staff_counts([tenant])[0]).data)


class RejectPaymentView(APIView):
    def post(self, request):
        submission_id = request.data.get("submission_id")
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)
        submission = TenantPaymentSubmission.objects.filter(pk=submission_id).first()
        if not submission:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)
        if submission.status != TenantPaymentSubmission.STATUS_PENDING:
            return Response({"detail": "Only pending submissions can be rejected."}, status=status.HTTP_400_BAD_REQUEST)
        reject_payment_submission(
            submission=submission,
            reason=reason,
            rejected_by=request.user.user,
        )
        write_audit(
            action="reject_payment",
            pharmacy_tin=submission.pharmacy_tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail=reason,
            metadata={
                "submission_id": submission.id,
                "payment_kind": submission.payment_kind,
            },
        )
        return Response(PaymentSubmissionSerializer(submission).data)


class ReleaseBillingHoldView(APIView):
    def post(self, request, tin):
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        tenant = release_billing_hold(tenant=tenant)
        write_audit(
            action="release_billing_hold",
            pharmacy_tin=tin,
            actor_username=getattr(request.user.user, "username", ""),
            detail="Released billing hold",
        )
        return Response(TenantSerializer(annotate_staff_counts([tenant])[0]).data)


class DashboardSummaryView(APIView):
    def get(self, request):
        from .models import (
            TenantFeedbackMessage,
        )

        inactive = TenantAccount.objects.filter(
            account_status__in=[
                TenantAccount.STATUS_SUSPENDED,
                TenantAccount.STATUS_BANNED,
                TenantAccount.STATUS_DELETED,
            ]
        ).count()
        return Response(
            {
                "tenants_total": TenantAccount.objects.count(),
                "tenants_active": TenantAccount.objects.filter(
                    account_status=TenantAccount.STATUS_ACTIVE
                ).count(),
                "suspended_tenants": TenantAccount.objects.filter(
                    account_status=TenantAccount.STATUS_SUSPENDED
                ).count(),
                "banned_tenants": TenantAccount.objects.filter(
                    account_status=TenantAccount.STATUS_BANNED
                ).count(),
                "inactive_tenants": inactive,
                "pending_setup_payments": TenantPaymentSubmission.objects.filter(
                    status=TenantPaymentSubmission.STATUS_PENDING,
                    payment_kind=TenantPaymentSubmission.KIND_SETUP,
                ).count(),
                "pending_quarterly_payments": TenantPaymentSubmission.objects.filter(
                    status=TenantPaymentSubmission.STATUS_PENDING,
                    payment_kind=TenantPaymentSubmission.KIND_QUARTERLY,
                ).count(),
                "pending_yearly_payments": TenantPaymentSubmission.objects.filter(
                    status=TenantPaymentSubmission.STATUS_PENDING,
                    payment_kind=TenantPaymentSubmission.KIND_YEARLY,
                ).count(),
                "setup_pending_tenants": TenantAccount.objects.filter(
                    setup_fee_approved=False
                ).count(),
                "unread_feedback": TenantFeedbackMessage.objects.filter(
                    sender_side=TenantFeedbackMessage.SIDE_TENANT,
                    read_by_apex=False,
                ).count(),
                "disabled_users": User.objects.filter(
                    is_active=False, is_staff=False, is_superuser=False
                ).count(),
            }
        )
