"""
Custom authentication backend that supports login by email OR username.

Owners (self-registered) have username == email.
Internal users (created by owner) may have a username that is not an email.

This backend tries to resolve the user by email first, then by username.
Preserves backward compatibility with existing email-based logins.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class UsernameOrEmailBackend(ModelBackend):
    """
    Authenticate by email OR username + password.

    Resolution order:
      1. Exact email match (case-insensitive) — covers owners.
      2. Exact username match — covers internal users.
    If the identifier matches both paths to different users, email wins
    (existing behaviour preservation).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        identifier = username  # Django's authenticate() sends the value as `username` kwarg

        # 1. Try email lookup (case-insensitive).
        user = User.objects.filter(email__iexact=identifier).first()

        # 2. Fall back to username lookup (exact, case-insensitive for safety).
        if user is None:
            user = User.objects.filter(username__iexact=identifier).first()

        if user is None:
            # Run the default hasher to mitigate timing attacks
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
