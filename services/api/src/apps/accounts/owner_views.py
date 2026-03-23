"""
Owner-only endpoints for access and role management.

These endpoints allow business owners to:
- View roles and permissions in their business
- Manage user accounts and credentials
- Audit access changes
"""
from __future__ import annotations

import secrets
import string
from typing import Dict, List

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.access import resolve_request_membership
from apps.accounts.models import Membership, AccessAuditLog
from apps.accounts.models import RolePermissionOverride
from apps.accounts.permissions import HasBusinessMembership
from apps.accounts.rbac import permissions_for_service, SERVICE_ROLE_PERMISSIONS
from apps.accounts.rbac_registry import get_registry
from apps.accounts.services import LastOwnerProtectionError, OwnerGuardService, InternalUserService
from apps.accounts.owner_serializers import (
    AccessSummarySerializer,
    CapabilitySerializer,
    RoleSummarySerializer,
    RoleDetailSerializer,
    UserAccountSerializer,
    PasswordResetResponseSerializer,
    AuditLogSerializer,
    get_role_description,
    BulkPermissionUpdateSerializer,
    PermissionUpdateResponseSerializer,
    CreateMemberSerializer,
    CreateMemberResponseSerializer,
    SetPasswordSerializer,
)
from apps.business.context import build_business_context

User = get_user_model()


def _is_owner(membership: Membership) -> bool:
    """Check if membership has owner role."""
    return membership and membership.role == 'owner'


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def _get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit to 500 chars


def _log_audit(
    action: str,
    actor: User,
    target_user: User,
    business,
    request: Request,
    details: Dict = None
) -> AccessAuditLog:
    """Create an audit log entry."""
    return AccessAuditLog.objects.create(
        action=action,
        actor=actor,
        target_user=target_user,
        business=business,
        details=details or {},
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )


def _generate_temporary_password(length: int = 12) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    # Ensure at least one uppercase, lowercase, and digit
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 3)]
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def access_summary(request: Request) -> Response:
    """
    GET /api/owner/access/summary/
    
    Returns the current user's roles and permissions with descriptions.
    Available to all authenticated users with business membership.
    """
    membership = resolve_request_membership(request)
    if not membership:
        return Response(
            {'error': 'No se encontró membresía activa'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    context = build_business_context(membership.business)
    service = context['service']
    
    # Get permissions for user's role
    permissions = permissions_for_service(service, membership.role)
    granted_perms = {code for code, granted in permissions.items() if granted}
    
    # Group by module with full capability details
    registry = get_registry()
    permissions_by_module = {}
    
    for cap in registry.get_by_service(service):
        if cap.module not in permissions_by_module:
            permissions_by_module[cap.module] = []
        
        permissions_by_module[cap.module].append({
            'code': cap.code,
            'title': cap.title,
            'description': cap.description,
            'granted': cap.code in granted_perms,
        })
    
    role_display = dict(Membership.ROLE_CHOICES).get(membership.role, membership.role)
    
    data = {
        'user_id': request.user.id,
        'role': membership.role,
        'role_display': role_display,
        'business_name': membership.business.name,
        'service': service,
        'permissions_by_module': permissions_by_module,
    }
    
    serializer = AccessSummarySerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def roles_list(request: Request) -> Response:
    """
    GET /api/owner/access/roles/
    
    Returns list of roles available in the business with user counts.
    Owner-only endpoint.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede acceder a esta función'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    context = build_business_context(membership.business)
    service = context['service']
    
    # Get role definitions for this service
    service_roles = SERVICE_ROLE_PERMISSIONS.get(service, {})
    
    # Get HQ for family membership count
    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    # Count users per role in the family
    role_counts = {}
    memberships = Membership.objects.filter(business__id__in=family_ids)
    for m in memberships:
        role_counts[m.role] = role_counts.get(m.role, 0) + 1
    
    roles_data = []
    for role_code, permissions in service_roles.items():
        role_display = dict(Membership.ROLE_CHOICES).get(role_code, role_code)
        roles_data.append({
            'role': role_code,
            'role_display': role_display,
            'user_count': role_counts.get(role_code, 0),
            'permission_count': len(permissions) if isinstance(permissions, set) else 0,
        })
    
    serializer = RoleSummarySerializer(roles_data, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def role_detail(request: Request, role: str) -> Response:
    """
    GET /api/owner/access/roles/:role/
    
    Returns detailed information about a specific role including
    permissions grouped by module and users assigned to this role.
    Owner-only endpoint.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede acceder a esta función'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    context = build_business_context(membership.business)
    service = context['service']
    
    # Validate role exists for this service
    service_roles = SERVICE_ROLE_PERMISSIONS.get(service, {})
    if role not in service_roles:
        return Response(
            {'error': f'El rol {role} no existe para el servicio {service}'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get permissions for this role (with business overrides if they exist)
    permissions = permissions_for_service(service, role, membership.business)
    granted_perms = {code for code, granted in permissions.items() if granted}
    
    # Group GRANTED permissions by module (for display)
    registry = get_registry()
    permissions_by_module = {}
    
    # Get ALL available permissions for this service grouped by module
    # This allows frontend to show toggles for enabling/disabling any permission
    all_permissions_by_module = {}
    
    for cap in registry.get_by_service(service):
        perm_data = {
            'code': cap.code,
            'title': cap.title,
            'description': cap.description,
            'enabled': cap.code in granted_perms,
        }
        
        # Add to "all permissions" dict (for editing)
        if cap.module not in all_permissions_by_module:
            all_permissions_by_module[cap.module] = []
        all_permissions_by_module[cap.module].append(perm_data)
        
        # Add to "permissions_by_module" only if granted (for read-only display)
        if cap.code in granted_perms:
            if cap.module not in permissions_by_module:
                permissions_by_module[cap.module] = []
            
            permissions_by_module[cap.module].append({
                'code': cap.code,
                'title': cap.title,
                'description': cap.description,
            })
    
    # Get users with this role in the business family
    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    memberships = Membership.objects.filter(
        business__id__in=family_ids,
        role=role
    ).select_related('user', 'business')
    
    users_data = []
    for m in memberships:
        user = m.user
        role_display = dict(Membership.ROLE_CHOICES).get(m.role, m.role)
        users_data.append({
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'role': m.role,
            'role_display': role_display,
            'is_active': user.is_active,
            'has_usable_password': user.has_usable_password(),
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        })
    
    role_display = dict(Membership.ROLE_CHOICES).get(role, role)
    description = get_role_description(role, service)
    
    data = {
        'role': role,
        'role_display': role_display,
        'description': description,
        'service': service,
        'permissions_by_module': all_permissions_by_module,  # Use all permissions with enabled flag
        'users': users_data,
    }
    
    serializer = RoleDetailSerializer(data)
    return Response(serializer.data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def update_role_permissions(request: Request, role: str) -> Response:
    """
    PUT/PATCH /api/v1/owner/access/roles/:role/permissions/
    
    Updates permissions for a specific role in the current business.
    Creates RolePermissionOverride records to customize permissions beyond defaults.
    
    Owner-only endpoint with audit logging.
    
    Request body:
    {
        "permissions": [
            {"permission": "view_sales", "enabled": true},
            {"permission": "manage_products", "enabled": false},
            ...
        ]
    }
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede modificar permisos'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Validate role exists
    if role == 'owner':
        return Response(
            {'error': 'No se pueden modificar los permisos del rol Owner'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    context = build_business_context(membership.business)
    service = context['service']
    
    service_roles = SERVICE_ROLE_PERMISSIONS.get(service, {})
    if role not in service_roles:
        return Response(
            {'error': f'El rol {role} no existe para el servicio {service}'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Validate request data
    serializer = BulkPermissionUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    permission_updates = serializer.validated_data['permissions']
    
    # Validate all permissions exist in registry
    registry = get_registry()
    valid_permissions = {cap.code for cap in registry.get_by_service(service)}
    
    for update in permission_updates:
        perm_code = update['permission']
        if perm_code not in valid_permissions:
            return Response(
                {'error': f'El permiso {perm_code} no existe para el servicio {service}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Apply updates: create or update RolePermissionOverride records
    updated_count = 0
    business = membership.business
    
    for update in permission_updates:
        perm_code = update['permission']
        enabled = update['enabled']
        
        override, created = RolePermissionOverride.objects.update_or_create(
            business=business,
            role=role,
            service=service,
            permission=perm_code,
            defaults={'enabled': enabled}
        )
        updated_count += 1
    
    # Log audit entry
    _log_audit(
        action='ROLE_PERMISSIONS_UPDATED',
        actor=request.user,
        target_user=request.user,  # Self-action
        business=business,
        request=request,
        details={
            'role': role,
            'service': service,
            'updated_permissions': [
                {'permission': u['permission'], 'enabled': u['enabled']} 
                for u in permission_updates
            ]
        }
    )
    
    # Return updated permissions grouped by module
    updated_permissions = permissions_for_service(service, role, business)
    granted_perms = {code for code, granted in updated_permissions.items() if granted}
    
    permissions_by_module = {}
    for cap in registry.get_by_service(service):
        if cap.code in granted_perms:
            if cap.module not in permissions_by_module:
                permissions_by_module[cap.module] = []
            
            permissions_by_module[cap.module].append({
                'code': cap.code,
                'title': cap.title,
                'description': cap.description,
            })
    
    response_data = {
        'success': True,
        'message': f'Se actualizaron {updated_count} permisos para el rol {role}',
        'role': role,
        'service': service,
        'updated_count': updated_count,
        'permissions_by_module': permissions_by_module,
    }
    
    response_serializer = PermissionUpdateResponseSerializer(response_data)
    return Response(response_serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def accounts_list(request: Request) -> Response:
    """
    GET /api/owner/access/accounts/
    
    Returns list of all user accounts in the business with their roles,
    status, and credential information (NOT actual passwords).
    Owner-only endpoint.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede acceder a esta función'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get all memberships in business family
    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    memberships = Membership.objects.filter(
        business__id__in=family_ids
    ).select_related('user', 'business').order_by('user__email')
    
    accounts_data = []
    for m in memberships:
        user = m.user
        role_display = dict(Membership.ROLE_CHOICES).get(m.role, m.role)
        accounts_data.append({
            'id': user.id,
            'email': user.email or '',
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'role': m.role,
            'role_display': role_display,
            'is_active': user.is_active,
            'has_usable_password': user.has_usable_password(),
            'membership_status': m.status,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        })
    
    serializer = UserAccountSerializer(accounts_data, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def create_member(request: Request) -> Response:
    """
    POST /api/v1/owner/access/accounts/create/

    Creates an internal user directly (no registration, no email verification,
    no onboarding, no business creation).

    The new user gets:
      - A Django User with username + hashed password
      - An active AccountProfile (email_verified=True)
      - A Membership in the owner's current business

    Owner-only endpoint with audit logging.

    Request body::

        {
            "first_name": "Juan",
            "last_name": "Pérez",
            "username": "juan.perez",
            "password": "securePass99",
            "role": "cashier",
            "email": ""  // optional
        }
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede crear usuarios internos'},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = CreateMemberSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        result = InternalUserService.create_internal_user(
            business=membership.business,
            first_name=data['first_name'],
            last_name=data['last_name'],
            username=data['username'],
            password=data['password'],
            role=data['role'],
            email=data.get('email', ''),
            created_by_user=request.user,
            request=request,
        )
    except DjangoValidationError as exc:
        # Extract message(s) from ValidationError
        messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
        return Response(
            {'error': messages[0] if len(messages) == 1 else messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_user = result['user']
    new_membership = result['membership']
    role_display = dict(Membership.ROLE_CHOICES).get(new_membership.role, new_membership.role)

    resp = CreateMemberResponseSerializer({
        'success': True,
        'message': f'Usuario "{new_user.username}" creado exitosamente con rol {role_display}.',
        'user_id': new_user.pk,
        'username': new_user.username,
        'full_name': new_user.get_full_name(),
        'role': new_membership.role,
        'role_display': role_display,
    })
    return Response(resp.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def reset_password(request: Request, user_id: int) -> Response:
    """
    POST /api/owner/access/accounts/:user_id/reset-password/
    
    Resets a user's password and returns a temporary password (shown only once).
    This is the ONLY endpoint that returns a password - it's temporary and meant
    to be shared with the user once.
    
    Owner-only endpoint with audit logging.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede resetear contraseñas'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get target user and verify they're in the same business family
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify target user belongs to same business family
    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    target_membership = Membership.objects.filter(
        user=target_user,
        business__id__in=family_ids
    ).first()
    
    if not target_membership:
        return Response(
            {'error': 'El usuario no pertenece a tu negocio'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Prevent owner from resetting their own password this way
    if target_user.id == request.user.id:
        return Response(
            {'error': 'No puedes resetear tu propia contraseña desde aquí. Usa "Olvidé mi contraseña"'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Allow owner to provide an explicit new password, or generate a temporary one.
    explicit_password = None
    if request.data:
        pw_serializer = SetPasswordSerializer(data=request.data)
        if pw_serializer.is_valid():
            explicit_password = pw_serializer.validated_data['new_password']

    if explicit_password:
        new_password = explicit_password
        password_type = 'explicit'
    else:
        new_password = _generate_temporary_password()
        password_type = 'temporary'
    
    # Set the password
    target_user.set_password(new_password)
    target_user.save()
    
    # Log the audit
    _log_audit(
        action='PASSWORD_RESET',
        actor=request.user,
        target_user=target_user,
        business=membership.business,
        request=request,
        details={
            'reset_by_owner': True,
            'target_email': target_user.email or target_user.username,
            'password_type': password_type,
        }
    )
    
    data = {
        'success': True,
        'message': 'Contraseña reseteada exitosamente.' + (
            ' Comparte esta contraseña temporal con el usuario.' if password_type == 'temporary' else ''
        ),
        'temporary_password': new_password if password_type == 'temporary' else '',
        'username': target_user.username,
        'email': target_user.email or '',
    }
    
    serializer = PasswordResetResponseSerializer(data)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def disable_account(request: Request, user_id: int) -> Response:
    """
    POST /api/owner/access/accounts/:user_id/disable/
    
    Disables a user account (sets is_active = False).
    Owner-only endpoint with audit logging.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede desactivar cuentas'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify target user belongs to same business family
    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    target_membership = Membership.objects.filter(
        user=target_user,
        business__id__in=family_ids
    ).first()
    
    if not target_membership:
        return Response(
            {'error': 'El usuario no pertenece a tu negocio'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if target_user.id == request.user.id:
        return Response(
            {'error': 'No puedes desactivar tu propia cuenta'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Last-owner guard: prevent disabling the only active owner in the business.
    if target_membership.role == 'owner':
        try:
            with transaction.atomic():
                OwnerGuardService.assert_not_last_owner(membership.business, target_user)
        except LastOwnerProtectionError as exc:
            _log_audit(
                action='ACCESS_DENIED',
                actor=request.user,
                target_user=target_user,
                business=membership.business,
                request=request,
                details={
                    'reason': 'last_owner_protection',
                    'attempted_action': 'disable_account',
                    'target_email': target_user.email,
                },
            )
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    # Toggle active status
    new_status = not target_user.is_active
    target_user.is_active = new_status
    target_user.save()

    # B.3: Sync AccountProfile.account_status to match Django's is_active flag.
    # 'suspended' ↔ 'active' keeps the two state stores consistent so that
    # HasBusinessMembership (subscription_status_enforcement gate) reflects the
    # same intent as the operator's action here.
    from apps.accounts.models import AccountProfile as _AccountProfile
    _AccountProfile.objects.filter(user=target_user).update(
        account_status=_AccountProfile.AccountStatus.ACTIVE if new_status else _AccountProfile.AccountStatus.SUSPENDED,
    )
    
    action = 'ACCOUNT_ENABLED' if new_status else 'ACCOUNT_DISABLED'
    
    _log_audit(
        action=action,
        actor=request.user,
        target_user=target_user,
        business=membership.business,
        request=request,
        details={
            'previous_status': not new_status,
            'new_status': new_status,
        }
    )
    
    message = 'Cuenta habilitada' if new_status else 'Cuenta deshabilitada'
    
    return Response({
        'success': True,
        'message': message,
        'is_active': new_status,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def audit_logs(request: Request) -> Response:
    """
    GET /api/owner/access/audit-logs/
    
    Returns audit log of access management actions.
    Owner-only endpoint.
    
    Query params:
    - limit: max records (default 50, max 200)
    - user_id: filter by target user
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede ver los logs de auditoría'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    limit = min(int(request.query_params.get('limit', 50)), 200)
    user_id = request.query_params.get('user_id')
    
    # Get logs for business
    logs = AccessAuditLog.objects.filter(
        business=membership.business
    ).select_related('actor', 'target_user')
    
    if user_id:
        logs = logs.filter(target_user__id=user_id)
    
    logs = logs[:limit]
    
    serializer = AuditLogSerializer(logs, many=True)
    return Response(serializer.data)


# ── Wave 2: B.1.a — Extended owner guard endpoints ────────────────────────────

@api_view(['PATCH'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def change_role(request: Request, user_id: int) -> Response:
    """
    PATCH /api/v1/owner/access/accounts/:user_id/role/

    Changes a member's role within the business family.

    Last-owner guard: if the target user is the sole active owner and the new
    role is not 'owner', the request is rejected with HTTP 409.

    Owner-only endpoint with audit logging.

    Request body::

        { "role": "manager" }
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede cambiar roles'},
            status=status.HTTP_403_FORBIDDEN,
        )

    new_role = request.data.get('role')
    valid_roles = [r for r, _ in Membership.ROLE_CHOICES]
    if not new_role or new_role not in valid_roles:
        return Response(
            {'error': f'Rol inválido. Opciones: {", ".join(valid_roles)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    target_membership = Membership.objects.filter(
        user=target_user, business__id__in=family_ids,
    ).first()

    if not target_membership:
        return Response({'error': 'El usuario no pertenece a tu negocio'}, status=status.HTTP_403_FORBIDDEN)

    if target_user.id == request.user.id:
        return Response(
            {'error': 'No puedes cambiar tu propio rol'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    previous_role = target_membership.role

    # Last-owner guard: only fires when demoting an owner to a non-owner role.
    if previous_role == 'owner' and new_role != 'owner':
        try:
            OwnerGuardService.assert_not_last_owner(membership.business, target_user)
        except LastOwnerProtectionError as exc:
            _log_audit(
                action='ACCESS_DENIED',
                actor=request.user,
                target_user=target_user,
                business=membership.business,
                request=request,
                details={
                    'reason': 'last_owner_protection',
                    'attempted_action': 'change_role',
                    'attempted_new_role': new_role,
                    'target_email': target_user.email,
                },
            )
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    target_membership.role = new_role
    target_membership.updated_by_user = request.user
    target_membership.save(update_fields=['role', 'updated_by_user', 'updated_at'])

    _log_audit(
        action='ROLE_CHANGED',
        actor=request.user,
        target_user=target_user,
        business=membership.business,
        request=request,
        details={
            'previous_role': previous_role,
            'new_role': new_role,
            'target_email': target_user.email,
        },
    )

    role_display = dict(Membership.ROLE_CHOICES).get(new_role, new_role)
    return Response({
        'success': True,
        'message': f'Rol actualizado a {role_display}',
        'user_id': target_user.id,
        'role': new_role,
        'role_display': role_display,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def suspend_member(request: Request, user_id: int) -> Response:
    """
    POST /api/v1/owner/access/accounts/:user_id/suspend/

    Toggles a Membership.status between ACTIVE ↔ SUSPENDED.
    Does not affect the underlying Django User (use disable_account for that).

    Last-owner guard: prevents suspending the sole active owner.

    Owner-only endpoint with audit logging.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede suspender membresías'},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    target_membership = Membership.objects.filter(
        user=target_user, business__id__in=family_ids,
    ).first()

    if not target_membership:
        return Response({'error': 'El usuario no pertenece a tu negocio'}, status=status.HTTP_403_FORBIDDEN)

    if target_user.id == request.user.id:
        return Response(
            {'error': 'No puedes suspender tu propia membresía'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Last-owner guard (only when suspending, not re-activating).
    if (target_membership.status == Membership.Status.ACTIVE
            and target_membership.role == 'owner'):
        try:
            OwnerGuardService.assert_not_last_owner(membership.business, target_user)
        except LastOwnerProtectionError as exc:
            _log_audit(
                action='ACCESS_DENIED',
                actor=request.user,
                target_user=target_user,
                business=membership.business,
                request=request,
                details={
                    'reason': 'last_owner_protection',
                    'attempted_action': 'suspend_member',
                    'target_email': target_user.email,
                },
            )
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    # Toggle membership status.
    if target_membership.status == Membership.Status.SUSPENDED:
        new_status = Membership.Status.ACTIVE
        action = 'MEMBER_REACTIVATED'
        message = 'Membresía reactivada'
    else:
        new_status = Membership.Status.SUSPENDED
        action = 'MEMBER_SUSPENDED'
        message = 'Membresía suspendida'

    previous_status = target_membership.status
    target_membership.status = new_status
    target_membership.updated_by_user = request.user
    target_membership.save(update_fields=['status', 'updated_by_user', 'updated_at'])

    _log_audit(
        action=action,
        actor=request.user,
        target_user=target_user,
        business=membership.business,
        request=request,
        details={
            'previous_status': previous_status,
            'new_status': new_status,
            'target_email': target_user.email,
        },
    )

    return Response({
        'success': True,
        'message': message,
        'membership_status': new_status,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
@transaction.atomic
def remove_member(request: Request, user_id: int) -> Response:
    """
    DELETE /api/v1/owner/access/accounts/:user_id/

    Permanently removes a Membership from the business family.
    The underlying User account is NOT deleted — only the access link.

    Last-owner guard: prevents removing the sole active owner.

    Owner-only endpoint with audit logging.
    """
    membership = resolve_request_membership(request)
    if not membership or not _is_owner(membership):
        return Response(
            {'error': 'Solo el propietario puede remover miembros'},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    hq = membership.business.parent if membership.business.parent else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    target_membership = Membership.objects.filter(
        user=target_user, business__id__in=family_ids,
    ).first()

    if not target_membership:
        return Response({'error': 'El usuario no pertenece a tu negocio'}, status=status.HTTP_403_FORBIDDEN)

    if target_user.id == request.user.id:
        return Response(
            {'error': 'No puedes remover tu propio acceso al negocio'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Last-owner guard: prevent removing the last active owner.
    if target_membership.role == 'owner' and target_membership.status == Membership.Status.ACTIVE:
        try:
            OwnerGuardService.assert_not_last_owner(membership.business, target_user)
        except LastOwnerProtectionError as exc:
            _log_audit(
                action='ACCESS_DENIED',
                actor=request.user,
                target_user=target_user,
                business=membership.business,
                request=request,
                details={
                    'reason': 'last_owner_protection',
                    'attempted_action': 'remove_member',
                    'target_email': target_user.email,
                },
            )
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    removed_role = target_membership.role
    removed_email = target_user.email or target_user.username
    target_membership.delete()

    _log_audit(
        action='MEMBER_REMOVED',
        actor=request.user,
        target_user=target_user,
        business=membership.business,
        request=request,
        details={
            'removed_role': removed_role,
            'target_email': removed_email,
        },
    )

    return Response({
        'success': True,
        'message': 'Miembro removido del negocio',
        'user_id': target_user.id,
        'email': removed_email,
    })
