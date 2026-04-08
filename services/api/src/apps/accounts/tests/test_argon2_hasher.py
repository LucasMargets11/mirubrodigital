"""
Tests for Phase 2B: Argon2 password hashing.

Covers:
  - T2B.1: New users get Argon2 hashes
  - T2B.2: Existing PBKDF2 users are transparently rehashed on login
  - T2B.3: Login works correctly with a legacy PBKDF2 hash
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile

User = get_user_model()

LOGIN_URL = '/api/v1/auth/login/'


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class Argon2HasherTests(TestCase):
    """Verify Argon2 is the primary hasher with transparent PBKDF2 fallback."""

    def test_new_user_password_is_argon2(self):
        """T2B.1: A newly created user's hash starts with 'argon2'."""
        user = User.objects.create_user(
            username='new@example.com',
            email='new@example.com',
            password='SecurePass123!',
        )
        self.assertTrue(
            user.password.startswith('argon2'),
            f'Expected argon2 hash, got: {user.password[:30]}…',
        )

    def test_login_works_with_old_pbkdf2_hash(self):
        """T2B.3: A user with a PBKDF2 hash can still log in."""
        pbkdf2_hash = make_password('SecurePass123!', hasher='pbkdf2_sha256')
        user = User.objects.create_user(
            username='legacy@example.com',
            email='legacy@example.com',
            password='unused',
        )
        # Force the password to a PBKDF2 hash directly in DB
        user.password = pbkdf2_hash
        user.save(update_fields=['password'])
        AccountProfile.objects.get_or_create(user=user)

        self.assertTrue(user.password.startswith('pbkdf2_sha256'))

        client = APIClient()
        resp = client.post(LOGIN_URL, {'email': 'legacy@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_existing_user_rehashes_to_argon2_on_login(self):
        """T2B.2: After login, a PBKDF2 hash is transparently upgraded to Argon2."""
        pbkdf2_hash = make_password('SecurePass123!', hasher='pbkdf2_sha256')
        user = User.objects.create_user(
            username='rehash@example.com',
            email='rehash@example.com',
            password='unused',
        )
        user.password = pbkdf2_hash
        user.save(update_fields=['password'])
        AccountProfile.objects.get_or_create(user=user)

        # Confirm it's PBKDF2 before login
        self.assertTrue(user.password.startswith('pbkdf2_sha256'))

        client = APIClient()
        resp = client.post(LOGIN_URL, {'email': 'rehash@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        # Reload from DB — Django should have rehashed on authenticate()
        user.refresh_from_db()
        self.assertTrue(
            user.password.startswith('argon2'),
            f'Expected argon2 after rehash, got: {user.password[:30]}…',
        )
