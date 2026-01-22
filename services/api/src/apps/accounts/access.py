from __future__ import annotations

from typing import List, Optional, Sequence

from django.conf import settings
from rest_framework.request import Request

from apps.business.context import build_business_context
from .models import Membership

BUSINESS_COOKIE_NAME = 'bid'
BUSINESS_COOKIE_MAX_AGE = getattr(settings, 'AUTH_COOKIE_REFRESH_MAX_AGE', 7 * 24 * 60 * 60)


def list_user_memberships(user) -> List[Membership]:
  return list(
    Membership.objects.select_related('business', 'business__subscription')
    .filter(user=user)
    .order_by('created_at')
  )


def select_membership(memberships: Sequence[Membership], requested_business_id: Optional[str]) -> Optional[Membership]:
  if not memberships:
    return None
  selected: Optional[Membership] = None
  if requested_business_id:
    requested_str = str(requested_business_id)
    selected = next((member for member in memberships if str(member.business_id) == requested_str), None)
  if selected is None and len(memberships) == 1:
    selected = memberships[0]
  if selected is None:
    selected = memberships[0]
  return selected


def _membership_cache(request: Request) -> List[Membership]:
  cached = getattr(request, '_memberships_cache', None)
  if cached is not None:
    return cached
  user = getattr(request, 'user', None)
  if not user or not user.is_authenticated:
    return []
  memberships = list_user_memberships(user)
  request._memberships_cache = memberships
  return memberships


def resolve_request_membership(request: Request) -> Optional[Membership]:
  membership = getattr(request, 'membership', None)
  if membership is not None:
    request.business = membership.business
    return membership
  memberships = _membership_cache(request)
  if not memberships:
    return None
  requested_business_id = request.COOKIES.get(BUSINESS_COOKIE_NAME)
  membership = select_membership(memberships, requested_business_id)
  if membership:
    request.membership = membership
    request.business = membership.business
  return membership


def resolve_business_context(request: Request, membership: Membership):
  context = getattr(request, '_business_context', None)
  if context is not None:
    return context
  context = build_business_context(membership.business)
  request._business_context = context
  request.active_service = context['service']
  return context
