from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import ACTOR_TYPE

User = get_user_model()


class ApexLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


def issue_apex_tokens(user) -> dict:
    now = datetime.now(timezone.utc)
    access_lifetime = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME", timedelta(hours=8))
    refresh_lifetime = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME", timedelta(days=7))
    algorithm = settings.SIMPLE_JWT.get("ALGORITHM", "HS256")

    access_payload = {
        "actor_type": ACTOR_TYPE,
        "user_id": user.pk,
        "username": user.username,
        "token_type": "access",
        "iat": now,
        "exp": now + access_lifetime,
    }
    refresh_payload = {
        "actor_type": ACTOR_TYPE,
        "user_id": user.pk,
        "username": user.username,
        "token_type": "refresh",
        "iat": now,
        "exp": now + refresh_lifetime,
    }

    full_name = f"{user.first_name} {user.last_name}".strip()

    return {
        "access": jwt.encode(access_payload, settings.SECRET_KEY, algorithm=algorithm),
        "refresh": jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=algorithm),
        "user": {
            "id": user.pk,
            "username": user.username,
            "full_name": full_name,
            "email": user.email or "",
            "is_superadmin": bool(user.is_superuser),
            "actor_type": ACTOR_TYPE,
        },
    }


class ApexLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ApexLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"].strip()
        password = serializer.validated_data["password"]

        user = authenticate(username=username, password=password)
        if user is None:
            # Case-insensitive username fallback for Django auth.
            matched = User.objects.filter(username__iexact=username).first()
            if matched and matched.check_password(password):
                user = matched

        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not (user.is_staff or user.is_superuser):
            return Response(
                {"detail": "Only staff/superuser accounts can access the Apex console."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(issue_apex_tokens(user))


class ApexMeView(APIView):
    def get(self, request):
        user = request.user.user
        full_name = f"{user.first_name} {user.last_name}".strip()
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "full_name": full_name,
                "email": user.email or "",
                "is_superadmin": bool(user.is_superuser),
                "actor_type": ACTOR_TYPE,
            }
        )
