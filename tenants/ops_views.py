"""Apex ops APIs: pricing, pharmacy chat, audit, users, analytics."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ApexAuditLog,
    SubscriptionPricingRule,
    TenantAccount,
    TenantFeedbackMessage,
    TenantFeedbackThread,
    TenantPaymentSubmission,
    UserProfile,
)
from .pricing import (
    build_modules_key,
    parse_modules,
    resolve_pricing,
    write_audit,
)

User = get_user_model()


class PricingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPricingRule
        fields = [
            "id",
            "business_type",
            "modules_key",
            "modules",
            "setup_fee_etb",
            "quarterly_fee_etb",
            "yearly_fee_etb",
            "description",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "modules_key", "created_at", "updated_at"]


class PricingRulesView(APIView):
    def get(self, request):
        qs = SubscriptionPricingRule.objects.all().order_by("sort_order", "business_type", "modules_key")
        return Response(PricingRuleSerializer(qs, many=True).data)

    def post(self, request):
        modules = parse_modules(request.data.get("modules") or [])
        business_type = (request.data.get("business_type") or "Pharmacy").strip() or "Pharmacy"
        modules_key = build_modules_key(modules)
        defaults = {
            "modules": modules_for_store(modules),
            "setup_fee_etb": int(request.data.get("setup_fee_etb") or 15000),
            "quarterly_fee_etb": int(request.data.get("quarterly_fee_etb") or 5000),
            "yearly_fee_etb": int(request.data.get("yearly_fee_etb") or 18000),
            "description": (request.data.get("description") or "").strip(),
            "is_active": bool(request.data.get("is_active", True)),
            "sort_order": int(request.data.get("sort_order") or 0),
        }
        rule, _ = SubscriptionPricingRule.objects.update_or_create(
            business_type=business_type,
            modules_key=modules_key,
            defaults=defaults,
        )
        write_audit(
            action="upsert_pricing_rule",
            actor_username=getattr(request.user.user, "username", ""),
            detail=f"{business_type} / {modules_key}",
            metadata={"rule_id": rule.id},
        )
        return Response(PricingRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


def modules_for_store(modules) -> list[str]:
    return sorted(set(parse_modules(modules)))


class PricingRuleDetailView(APIView):
    def patch(self, request, pk):
        rule = SubscriptionPricingRule.objects.filter(pk=pk).first()
        if not rule:
            return Response({"detail": "Rule not found."}, status=status.HTTP_404_NOT_FOUND)
        if "modules" in request.data:
            modules = parse_modules(request.data.get("modules"))
            rule.modules = modules_for_store(modules)
            rule.modules_key = build_modules_key(modules)
        for field in (
            "business_type",
            "setup_fee_etb",
            "quarterly_fee_etb",
            "yearly_fee_etb",
            "description",
            "is_active",
            "sort_order",
        ):
            if field in request.data:
                setattr(rule, field, request.data[field])
        if "business_type" in request.data:
            rule.business_type = (request.data.get("business_type") or "Pharmacy").strip()
        rule.save()
        write_audit(
            action="set_pricing_rule_active"
            if "is_active" in request.data and len(request.data.keys()) == 1
            else "upsert_pricing_rule",
            actor_username=getattr(request.user.user, "username", ""),
            detail=f"{rule.business_type} / {rule.modules_key}",
            metadata={"rule_id": rule.id, "is_active": rule.is_active},
        )
        return Response(PricingRuleSerializer(rule).data)

    def delete(self, request, pk):
        rule = SubscriptionPricingRule.objects.filter(pk=pk).first()
        if not rule:
            return Response({"detail": "Rule not found."}, status=status.HTTP_404_NOT_FOUND)
        rule.delete()
        write_audit(
            action="delete_pricing_rule",
            actor_username=getattr(request.user.user, "username", ""),
            detail=f"rule {pk}",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PricingPreviewView(APIView):
    def get(self, request):
        modules = request.query_params.getlist("modules") or parse_modules(
            request.query_params.get("modules")
        )
        business_type = request.query_params.get("business_type") or "Pharmacy"
        return Response(resolve_pricing(business_type, modules))


class FeedbackDirectoryView(APIView):
    def get(self, request):
        tenants = TenantAccount.objects.exclude(
            account_status=TenantAccount.STATUS_DELETED
        ).order_by("pharmacy_name")
        threads = {
            t.pharmacy_tin: t
            for t in TenantFeedbackThread.objects.all()
        }
        unread = {
            row["thread__pharmacy_tin"]: row["c"]
            for row in TenantFeedbackMessage.objects.filter(
                sender_side=TenantFeedbackMessage.SIDE_TENANT,
                read_by_apex=False,
            )
            .values("thread__pharmacy_tin")
            .annotate(c=Count("id"))
        }
        last_msg = {
            row["thread__pharmacy_tin"]: row["last"]
            for row in TenantFeedbackMessage.objects.values("thread__pharmacy_tin").annotate(
                last=Max("created_at")
            )
        }
        # Latest message body/sender per TIN for conversation previews
        last_preview: dict[str, dict] = {}
        for msg in (
            TenantFeedbackMessage.objects.select_related("thread")
            .order_by("-created_at")
            .only("body", "sender_side", "created_at", "thread__pharmacy_tin")
        ):
            tin = msg.thread.pharmacy_tin
            if tin in last_preview:
                continue
            last_preview[tin] = {
                "body": msg.body,
                "sender_side": msg.sender_side,
                "created_at": msg.created_at,
            }

        rows = []
        for tenant in tenants:
            thread = threads.get(tenant.pharmacy_tin)
            preview = last_preview.get(tenant.pharmacy_tin)
            rows.append(
                {
                    "pharmacy_tin": tenant.pharmacy_tin,
                    "pharmacy_name": tenant.pharmacy_name,
                    "logo_url": tenant.logo_url or "",
                    "account_status": tenant.account_status,
                    "thread_id": thread.id if thread else None,
                    "thread_status": thread.status if thread else None,
                    "unread_count": unread.get(tenant.pharmacy_tin, 0),
                    "last_message_at": last_msg.get(tenant.pharmacy_tin),
                    "last_message": preview,
                }
            )
        rows.sort(
            key=lambda r: (
                0 if r["unread_count"] else 1,
                -(r["last_message_at"].timestamp() if r["last_message_at"] else 0),
                r["pharmacy_name"] or r["pharmacy_tin"],
            )
        )
        return Response(rows)


class FeedbackThreadView(APIView):
    def get(self, request, tin):
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=404)
        thread, _ = TenantFeedbackThread.objects.get_or_create(pharmacy_tin=tin)
        messages = thread.messages.all()
        TenantFeedbackMessage.objects.filter(
            thread=thread,
            sender_side=TenantFeedbackMessage.SIDE_TENANT,
            read_by_apex=False,
        ).update(read_by_apex=True)
        return Response(
            {
                "thread": {
                    "id": thread.id,
                    "pharmacy_tin": thread.pharmacy_tin,
                    "status": thread.status,
                    "pharmacy_name": tenant.pharmacy_name,
                },
                "messages": [
                    {
                        "id": m.id,
                        "sender_side": m.sender_side,
                        "body": m.body,
                        "image_url": m.image_url,
                        "sender_username": m.sender_username,
                        "created_at": m.created_at,
                        "read_by_tenant": m.read_by_tenant,
                        "read_by_apex": m.read_by_apex,
                    }
                    for m in messages
                ],
            }
        )


class SendFeedbackMessageView(APIView):
    def post(self, request, tin):
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "Message body is required."}, status=400)
        tenant = TenantAccount.objects.filter(pharmacy_tin=tin).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=404)
        thread, _ = TenantFeedbackThread.objects.get_or_create(pharmacy_tin=tin)
        if thread.status == TenantFeedbackThread.STATUS_CLOSED:
            thread.status = TenantFeedbackThread.STATUS_OPEN
            thread.closed_at = None
            thread.save(update_fields=["status", "closed_at", "updated_at"])
        msg = TenantFeedbackMessage.objects.create(
            thread=thread,
            sender_side=TenantFeedbackMessage.SIDE_APEX,
            body=body,
            image_url=(request.data.get("image_url") or "").strip(),
            sender_username=getattr(request.user.user, "username", ""),
            read_by_apex=True,
            read_by_tenant=False,
        )
        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])
        return Response(
            {
                "id": msg.id,
                "sender_side": msg.sender_side,
                "body": msg.body,
                "image_url": msg.image_url,
                "sender_username": msg.sender_username,
                "created_at": msg.created_at,
            },
            status=201,
        )


class StartChatView(APIView):
    def post(self, request):
        tin = (request.data.get("pharmacy_tin") or "").strip()
        body = (request.data.get("body") or "").strip()
        if not tin or not body:
            return Response({"detail": "pharmacy_tin and body are required."}, status=400)
        if not TenantAccount.objects.filter(pharmacy_tin=tin).exists():
            return Response({"detail": "Tenant not found."}, status=404)
        thread, _ = TenantFeedbackThread.objects.get_or_create(pharmacy_tin=tin)
        msg = TenantFeedbackMessage.objects.create(
            thread=thread,
            sender_side=TenantFeedbackMessage.SIDE_APEX,
            body=body,
            sender_username=getattr(request.user.user, "username", ""),
            read_by_apex=True,
            read_by_tenant=False,
        )
        return Response({"thread_id": thread.id, "message_id": msg.id, "pharmacy_tin": tin}, status=201)


class BroadcastChatView(APIView):
    def post(self, request):
        body = (request.data.get("body") or "").strip()
        tins = request.data.get("pharmacy_tins") or []
        if not body or not isinstance(tins, list) or not tins:
            return Response({"detail": "body and pharmacy_tins are required."}, status=400)
        created = 0
        for tin in tins:
            tin = str(tin).strip()
            if not TenantAccount.objects.filter(pharmacy_tin=tin).exists():
                continue
            thread, _ = TenantFeedbackThread.objects.get_or_create(pharmacy_tin=tin)
            TenantFeedbackMessage.objects.create(
                thread=thread,
                sender_side=TenantFeedbackMessage.SIDE_APEX,
                body=body,
                sender_username=getattr(request.user.user, "username", ""),
                read_by_apex=True,
                read_by_tenant=False,
            )
            created += 1
        write_audit(
            action="broadcast_chat",
            actor_username=getattr(request.user.user, "username", ""),
            detail=body[:200],
            metadata={"count": created},
        )
        return Response({"sent": created})


class CloseThreadView(APIView):
    def post(self, request, tin):
        thread = TenantFeedbackThread.objects.filter(pharmacy_tin=tin).first()
        if not thread:
            return Response({"detail": "Thread not found."}, status=404)
        thread.status = TenantFeedbackThread.STATUS_CLOSED
        thread.closed_at = timezone.now()
        thread.closed_by = request.user.user
        thread.save()
        return Response({"status": thread.status})


class AuditLogView(APIView):
    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get("limit") or 200), 1), 500)
        except (TypeError, ValueError):
            limit = 200
        qs = ApexAuditLog.objects.all().order_by("-created_at")[:limit]
        return Response(
            [
                {
                    "id": row.id,
                    "action": row.action,
                    "pharmacy_tin": row.pharmacy_tin,
                    "actor_username": row.actor_username,
                    "detail": row.detail,
                    "metadata": row.metadata or {},
                    "created_at": row.created_at,
                }
                for row in qs
            ]
        )


class TenantUsersView(APIView):
    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        qs = UserProfile.objects.select_related("user").all().order_by("-updated_at")
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search)
                | Q(pharmacy_tin__icontains=search)
                | Q(pharmacy_name__icontains=search)
            )
        rows = []
        for p in qs[:300]:
            rows.append(
                {
                    "id": p.user_id,
                    "username": p.user.username,
                    "role": p.role,
                    "pharmacy_tin": p.pharmacy_tin,
                    "pharmacy_name": p.pharmacy_name,
                    "is_active": p.user.is_active,
                    "login_disabled": not p.user.is_active,
                }
            )
        return Response(rows)


class SetUserLoginDisabledView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        disabled = bool(request.data.get("disabled", True))
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=404)
        if user.is_staff or user.is_superuser:
            return Response({"detail": "Cannot disable Apex staff accounts."}, status=400)
        user.is_active = not disabled
        user.save(update_fields=["is_active"])
        profile = UserProfile.objects.filter(user=user).first()
        write_audit(
            action="disable_user_login" if disabled else "enable_user_login",
            pharmacy_tin=getattr(profile, "pharmacy_tin", "") or "",
            actor_username=getattr(request.user.user, "username", ""),
            detail=f"{user.username} login {'disabled' if disabled else 'enabled'}",
            metadata={"user_id": user.id, "username": user.username},
        )
        return Response({"user_id": user.id, "login_disabled": disabled, "is_active": user.is_active})


class AnalyticsSummaryView(APIView):
    def get(self, request):
        by_status = (
            TenantAccount.objects.values("account_status")
            .annotate(count=Count("id"))
            .order_by()
        )
        payments_by_kind = (
            TenantPaymentSubmission.objects.filter(status="approved")
            .values("payment_kind")
            .annotate(count=Count("id"))
            .order_by()
        )
        return Response(
            {
                "tenants_by_status": {r["account_status"]: r["count"] for r in by_status},
                "approved_payments_by_kind": {
                    r["payment_kind"]: r["count"] for r in payments_by_kind
                },
                "open_threads": TenantFeedbackThread.objects.filter(status="open").count(),
                "pricing_rules_active": SubscriptionPricingRule.objects.filter(is_active=True).count(),
            }
        )


class SignupsPipelineView(APIView):
    """Tenants registered in the current calendar month, with setup review status."""

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tenants = list(
            TenantAccount.objects.filter(created_at__gte=month_start)
            .exclude(is_illustration=True)
            .order_by("-created_at")
        )
        tins = [t.pharmacy_tin for t in tenants]

        managers: dict[str, str] = {}
        for p in UserProfile.objects.filter(
            pharmacy_tin__in=tins,
            role__iexact="manager",
        ).select_related("user"):
            managers.setdefault(p.pharmacy_tin, p.user.username)

        pending_by_tin = {
            p.pharmacy_tin: p
            for p in TenantPaymentSubmission.objects.filter(
                pharmacy_tin__in=tins,
                payment_kind=TenantPaymentSubmission.KIND_SETUP,
                status=TenantPaymentSubmission.STATUS_PENDING,
            )
        }

        # Latest setup submission per TIN (any status) for rejected detection
        latest_setup: dict[str, TenantPaymentSubmission] = {}
        for p in TenantPaymentSubmission.objects.filter(
            pharmacy_tin__in=tins,
            payment_kind=TenantPaymentSubmission.KIND_SETUP,
        ).order_by("-submitted_at"):
            latest_setup.setdefault(p.pharmacy_tin, p)

        rows = []
        for t in tenants:
            pending = pending_by_tin.get(t.pharmacy_tin)
            latest = latest_setup.get(t.pharmacy_tin)

            if t.setup_fee_approved:
                status_key = "approved"
            elif pending is not None:
                status_key = "pending"
            elif latest is not None and latest.status == TenantPaymentSubmission.STATUS_REJECTED:
                status_key = "rejected"
            else:
                # Created this month, setup not approved, no pending submission
                status_key = "pending"

            rows.append(
                {
                    "pharmacy_tin": t.pharmacy_tin,
                    "pharmacy_name": t.pharmacy_name,
                    "created_at": t.created_at,
                    "setup_fee_etb": t.setup_fee_etb,
                    "free_trial_ends_at": t.free_trial_ends_at,
                    "payment_transaction_ref": (
                        (pending.transaction_ref if pending else None)
                        or t.payment_transaction_ref
                        or (latest.transaction_ref if latest else "")
                        or ""
                    ),
                    "payment_channel": (
                        (pending.payment_channel if pending else None)
                        or t.payment_channel
                        or (latest.payment_channel if latest else "")
                        or ""
                    ),
                    "has_pending_submission": pending is not None,
                    "pending_setup_payment_id": pending.id if pending else None,
                    "status": status_key,
                    "manager_username": managers.get(t.pharmacy_tin, ""),
                }
            )
        return Response(rows)
