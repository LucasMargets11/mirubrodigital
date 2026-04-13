"""
Google OAuth service — validates Google ID tokens and extracts user info.

Uses the official google-auth library to verify ID tokens against Google's
public keys.  The token is validated for:
  - Signature (RS256, fetched from Google's JWKS endpoint)
  - Expiration
  - Audience (must match GOOGLE_OAUTH_CLIENT_ID)
  - Issuer (accounts.google.com or https://accounts.google.com)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

# Cache the transport session across calls (reuses HTTP connections).
_transport = google_requests.Request()


@dataclass(frozen=True)
class GoogleTokenPayload:
    sub: str
    email: str
    email_verified: bool
    name: str = ''
    given_name: str = ''
    family_name: str = ''
    picture: str = ''


@dataclass(frozen=True)
class GoogleVerifyResult:
    valid: bool
    payload: Optional[GoogleTokenPayload] = None
    error: str = ''


class GoogleOAuthService:

    @staticmethod
    def verify_token(credential: str) -> GoogleVerifyResult:
        """Verify a Google ID token and return extracted user info.

        Returns GoogleVerifyResult with valid=False and a descriptive error
        on any failure (bad token, wrong audience, expired, etc.).
        """
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        if not client_id:
            logger.error('[GoogleOAuth] GOOGLE_OAUTH_CLIENT_ID is not configured')
            return GoogleVerifyResult(valid=False, error='server_config')

        try:
            idinfo = id_token.verify_oauth2_token(
                credential,
                _transport,
                audience=client_id,
            )
        except ValueError as exc:
            logger.info('[GoogleOAuth] Token verification failed: %s', exc)
            return GoogleVerifyResult(valid=False, error='invalid_token')

        # Extract fields
        email = idinfo.get('email', '').lower().strip()
        email_verified = idinfo.get('email_verified', False)
        sub = idinfo.get('sub', '')

        if not email or not sub:
            return GoogleVerifyResult(valid=False, error='missing_claims')

        return GoogleVerifyResult(
            valid=True,
            payload=GoogleTokenPayload(
                sub=sub,
                email=email,
                email_verified=email_verified,
                name=idinfo.get('name', ''),
                given_name=idinfo.get('given_name', ''),
                family_name=idinfo.get('family_name', ''),
                picture=idinfo.get('picture', ''),
            ),
        )
