"""
Structured security event logger for auth telemetry.

All auth-related events are emitted through a dedicated ``apps.accounts.security``
logger so they can be filtered, aggregated, and turned into metrics by any log
backend (CloudWatch Logs Insights, ELK, Datadog, etc.).

Each event carries a consistent ``event`` field suitable for metric derivation:

  auth.login.success        – successful owner/public login
  auth.login.failed         – bad credentials or inactive user
  auth.logout.success       – explicit logout (token blacklisted)
  auth.refresh.success      – refresh token rotated
  auth.refresh.failed       – invalid / expired / replayed refresh token
  auth.ratelimit.triggered  – 3D rate-limiter blocked a request
"""
from __future__ import annotations

import logging
from typing import Any

security_logger = logging.getLogger('apps.accounts.security')


def _emit(
    level: int,
    *,
    event: str,
    outcome: str,
    user_id: int | None = None,
    email: str | None = None,
    ip: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a structured security event."""
    data: dict[str, Any] = {
        'event': event,
        'outcome': outcome,
    }
    if user_id is not None:
        data['user_id'] = user_id
    if email:
        data['email'] = email
    if ip:
        data['ip'] = ip
    if reason:
        data['reason'] = reason
    if extra:
        data.update(extra)

    security_logger.log(level, '%s %s', event, outcome, extra=data)


# ── Public helpers ───────────────────────────────────────────────────────────

def login_success(*, user_id: int, email: str, ip: str) -> None:
    _emit(logging.INFO, event='auth.login.success', outcome='success',
          user_id=user_id, email=email, ip=ip)


def login_failed(*, email: str, ip: str, reason: str = 'invalid_credentials') -> None:
    _emit(logging.WARNING, event='auth.login.failed', outcome='failed',
          email=email, ip=ip, reason=reason)


def logout_success(*, user_id: int | None = None, ip: str | None = None) -> None:
    _emit(logging.INFO, event='auth.logout.success', outcome='success',
          user_id=user_id, ip=ip)


def refresh_success(*, user_id: int, ip: str) -> None:
    _emit(logging.INFO, event='auth.refresh.success', outcome='success',
          user_id=user_id, ip=ip)


def refresh_failed(*, ip: str, reason: str = 'invalid_token') -> None:
    _emit(logging.WARNING, event='auth.refresh.failed', outcome='failed',
          ip=ip, reason=reason)


def ratelimit_triggered(*, ip: str, email: str | None = None, reason: str = '') -> None:
    _emit(logging.WARNING, event='auth.ratelimit.triggered', outcome='blocked',
          ip=ip, email=email, reason=reason)
