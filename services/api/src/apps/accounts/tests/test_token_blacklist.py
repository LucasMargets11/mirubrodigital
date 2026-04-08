"""
Tests for Phase 2A: Token blacklist — refresh‑token replay prevention
and server‑side revocation on logout.

Covers:
  - T2A.1: Logout blacklists the refresh token server‑side
  - T2A.2: Refresh blacklists the old refresh token (replay prevention)
  - T2A.3: Logout without a refresh cookie does not error
  - T2A.4: Logout with an expired / invalid / already‑blacklisted token
            does not error
"""
import json
from base64 import urlsafe_b64decode

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AccountProfile

User = get_user_model()

LOGIN_URL = '/api/v1/auth/login/'
LOGOUT_URL = '/api/v1/auth/logout/'
REFRESH_URL = '/api/v1/auth/refresh/'


def _create_user(email='owner@test.com', password='SecurePass123!'):
    user = User.objects.create_user(username=email, email=email, password=password)
    AccountProfile.objects.get_or_create(user=user)
    return user


def _login(client, email='owner@test.com', password='SecurePass123!'):
    """Login and return the response (cookies are set on the client)."""
    return client.post(LOGIN_URL, {'email': email, 'password': password})


def _extract_jti(raw_token: str) -> str:
    """Decode the JWT payload without verification to extract the jti claim."""
    payload_b64 = raw_token.split('.')[1]
    # Add padding
    payload_b64 += '=' * (-len(payload_b64) % 4)
    payload = json.loads(urlsafe_b64decode(payload_b64))
    return payload['jti']


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class LogoutBlacklistTests(TestCase):
    """T2A.1 / T2A.3 / T2A.4 — Logout revokes refresh token server‑side."""

    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()

    # ── T2A.1: logout blacklists the current refresh token ───────────────

    def test_logout_blacklists_refresh_token(self):
        _login(self.client)
        # Grab the raw refresh cookie that was just set
        raw_refresh = self.client.cookies['refresh_token'].value
        self.assertTrue(raw_refresh)

        # Logout
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.json()['status'], 'logged_out')

        # The token should now be blacklisted in the DB
        jti = _extract_jti(raw_refresh)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=jti).exists(),
            'Refresh token was NOT blacklisted after logout',
        )

    def test_reusing_refresh_after_logout_fails(self):
        _login(self.client)
        raw_refresh = self.client.cookies['refresh_token'].value

        # Logout (blacklists the token)
        self.client.post(LOGOUT_URL)

        # Try to use the old refresh token — must be rejected
        self.client.cookies['refresh_token'] = raw_refresh
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)

    # ── T2A.3: logout without a refresh cookie doesn't break ─────────────

    def test_logout_without_cookie_is_ok(self):
        # No login, no cookie — should still return 200
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.json()['status'], 'logged_out')

    # ── T2A.4: logout with invalid / expired / already‑blacklisted token ─

    def test_logout_with_garbage_token_is_ok(self):
        self.client.cookies['refresh_token'] = 'not-a-jwt'
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_logout_with_already_blacklisted_token_is_ok(self):
        _login(self.client)
        raw_refresh = self.client.cookies['refresh_token'].value

        # Blacklist it manually first
        token = RefreshToken(raw_refresh)
        token.blacklist()

        # Logout again with same cookie — must NOT 500
        self.client.cookies['refresh_token'] = raw_refresh
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_logout_clears_cookies(self):
        _login(self.client)
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        # Django test client exposes Set-Cookie via resp.cookies
        # Deleted cookies have max-age=0
        for name in ('access_token', 'refresh_token'):
            cookie = resp.cookies.get(name)
            self.assertIsNotNone(cookie, f'Cookie {name} not set in response')
            self.assertEqual(cookie['max-age'], 0, f'Cookie {name} was not deleted')


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class RefreshBlacklistTests(TestCase):
    """T2A.2 — Refresh rotation blacklists the old token (replay prevention)."""

    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()

    def test_refresh_blacklists_old_token(self):
        _login(self.client)
        raw_refresh_v1 = self.client.cookies['refresh_token'].value

        # Perform a refresh — should succeed and issue new cookies
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.json()['status'], 'refreshed')

        # Old token should now be blacklisted
        jti = _extract_jti(raw_refresh_v1)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=jti).exists(),
            'Old refresh token was NOT blacklisted after rotation',
        )

    def test_replaying_old_refresh_after_rotation_fails(self):
        _login(self.client)
        raw_refresh_v1 = self.client.cookies['refresh_token'].value

        # First refresh — succeeds
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        # Try replaying the old token — must fail
        self.client.cookies['refresh_token'] = raw_refresh_v1
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_new_refresh_token_works_after_rotation(self):
        _login(self.client)

        # Rotate once
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        raw_refresh_v2 = self.client.cookies['refresh_token'].value

        # The new token should work for another refresh
        self.client.cookies['refresh_token'] = raw_refresh_v2
        resp2 = self.client.post(REFRESH_URL)
        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)

    def test_refresh_with_missing_cookie_returns_401(self):
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_garbage_token_returns_401(self):
        self.client.cookies['refresh_token'] = 'garbage'
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)
