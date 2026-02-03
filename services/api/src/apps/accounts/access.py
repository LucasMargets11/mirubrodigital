from __future__ import annotations

from typing import List, Optional, Sequence

from django.conf import settings
from rest_framework.request import Request

from apps.business.context import build_business_context
from apps.business.models import Business
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


def _try_resolve_inherited_membership(memberships: List[Membership], requested_id: str, request: Request) -> Optional[Membership]:
    """
    Attempts to resolve access to a branch for an HQ owner/admin who doesn't have direct membership.
    """
    try:
        # Optimization: verify exists and parent check
        # We need to fetch it to check parent
        target_business = Business.objects.filter(pk=requested_id).select_related('parent').first()
    except (ValueError, TypeError):
        return None
        
    if not target_business or not target_business.parent: 
        return None # Not found or is not a branch
        
    parent_id = target_business.parent.id
    # Check if user has membership in the parent business
    parent_membership = next((m for m in memberships if m.business_id == parent_id), None)
    
    # Only Owner/Admin of HQ can inherit access
    if parent_membership and parent_membership.role in ['owner', 'admin']:
        # Set the target business as the active business
        request.business = target_business
        return parent_membership
        
    return None


def resolve_request_membership(request: Request) -> Optional[Membership]:
  membership = getattr(request, 'membership', None)
  if membership is not None:
    # If already resolved, ensure business is set (might be branch or normal)
    if not getattr(request, 'business', None):
         request.business = membership.business
    return membership

  memberships = _membership_cache(request)
  if not memberships:
    return None

  # Support header for API clients, fallback to cookie
  requested_business_id = request.META.get('HTTP_X_BUSINESS_ID') or request.COOKIES.get(BUSINESS_COOKIE_NAME)
  
  # 1. Try direct membership match
  membership = select_membership(memberships, requested_business_id)
  
  # 2. If mismatch (fallback occurred) OR no selection, check inheritance for strict requested ID
  if requested_business_id:
      # If the selected membership is NOT the one requested, it means direct lookup failed.
      if membership.business_id != int(requested_business_id) if requested_business_id.isdigit() else str(membership.business_id) != requested_business_id:
          inherited = _try_resolve_inherited_membership(memberships, requested_business_id, request)
          if inherited:
              membership = inherited
              # request.business is set inside _try_resolve_inherited_membership
          else:
              # Fallback to the one select_membership picked
              request.business = membership.business
      else:
           # Exact match
           request.business = membership.business
  else:
      # No request, just fallback
      request.business = membership.business

  if membership:
    request.membership = membership

  return membership




def resolve_business_context(request: Request, membership: Membership):
  context = getattr(request, '_business_context', None)
  if context is not None:
    return context
  context = build_business_context(membership.business)
  request._business_context = context
  request.active_service = context['service']
  return context
