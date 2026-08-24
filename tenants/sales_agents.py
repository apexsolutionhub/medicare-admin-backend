from django.db.models import Count
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SalesAgent


class SalesAgentSerializer(serializers.ModelSerializer):
    displayName = serializers.CharField(source="display_name", max_length=255)
    isActive = serializers.BooleanField(source="is_active", required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    tenantCount = serializers.IntegerField(read_only=True)

    class Meta:
        model = SalesAgent
        fields = [
            "id",
            "displayName",
            "phone",
            "email",
            "city",
            "notes",
            "isActive",
            "createdAt",
            "tenantCount",
        ]

    def to_internal_value(self, data):
        payload = dict(data)
        if "id" in payload:
            payload.pop("id", None)
        return super().to_internal_value(payload)


def annotated_agents():
    return SalesAgent.objects.annotate(tenantCount=Count("tenants"))


def resolve_sales_agent(sales_agent_id):
    if sales_agent_id in (None, "", 0, "0"):
        return None
    try:
        pk = int(sales_agent_id)
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({"sales_agent_id": ["Invalid sales agent."]}) from exc
    agent = SalesAgent.objects.filter(pk=pk, is_active=True).first()
    if agent is None:
        raise serializers.ValidationError({"sales_agent_id": ["Unknown or inactive sales agent."]})
    return agent


class PublicSalesAgentsView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = annotated_agents().filter(is_active=True).order_by("display_name")
        return Response(SalesAgentSerializer(qs, many=True).data)


class ApexSalesAgentListView(APIView):
    def get(self, request):
        active_only = str(request.query_params.get("active_only") or "").lower() in {"1", "true"}
        qs = annotated_agents().order_by("display_name")
        if active_only:
            qs = qs.filter(is_active=True)
        return Response(SalesAgentSerializer(qs, many=True).data)

    def post(self, request):
        pk = request.data.get("id")
        if pk:
            agent = SalesAgent.objects.filter(pk=pk).first()
            if agent is None:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = SalesAgentSerializer(agent, data=request.data, partial=True)
        else:
            serializer = SalesAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = serializer.save()
        agent = annotated_agents().get(pk=agent.pk)
        return Response(
            SalesAgentSerializer(agent).data,
            status=status.HTTP_200_OK if pk else status.HTTP_201_CREATED,
        )


class ApexSalesAgentDetailView(APIView):
    def patch(self, request, pk):
        agent = SalesAgent.objects.filter(pk=pk).first()
        if agent is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if "isActive" in request.data or "is_active" in request.data:
            raw = request.data.get("isActive", request.data.get("is_active"))
            agent.is_active = bool(raw) if not isinstance(raw, str) else raw.lower() in {"1", "true", "yes"}
            agent.save(update_fields=["is_active", "updated_at"])
        else:
            serializer = SalesAgentSerializer(agent, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        agent = annotated_agents().get(pk=pk)
        return Response(SalesAgentSerializer(agent).data)

    def delete(self, request, pk):
        agent = SalesAgent.objects.filter(pk=pk).first()
        if agent is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        agent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
