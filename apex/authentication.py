from dataclasses import dataclass

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

ACTOR_TYPE = "apex"
User = get_user_model()


@dataclass
class ApexPrincipal:
    user: object
    actor_type: str = ACTOR_TYPE

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def pk(self):
        return self.user.pk

    @property
    def id(self):
        return self.user.pk

    @property
    def username(self):
        return self.user.username

    @property
    def is_superadmin(self) -> bool:
        return bool(getattr(self.user, "is_superuser", False))


class ApexJWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token = parts[1]
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.SIMPLE_JWT.get("ALGORITHM", "HS256")],
            )
        except jwt.PyJWTError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc

        if payload.get("actor_type") != ACTOR_TYPE:
            raise exceptions.AuthenticationFailed("Not an Apex platform token.")

        user_id = payload.get("user_id") or payload.get("member_id")
        if not user_id:
            raise exceptions.AuthenticationFailed("Invalid token payload.")

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("User not found or inactive.") from exc

        if not (user.is_staff or user.is_superuser):
            raise exceptions.AuthenticationFailed("Not authorized for Apex console.")

        return (ApexPrincipal(user=user), token)
