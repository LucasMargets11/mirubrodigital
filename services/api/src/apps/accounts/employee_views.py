"""
accounts/employee_views.py — Employee management and operative login.

Admin endpoints (require admin User + Membership):
  GET/POST  /api/v1/owner/employees/
  GET/PATCH /api/v1/owner/employees/:id/
  POST      /api/v1/owner/employees/:id/reset-pin/
  POST      /api/v1/owner/employees/:id/suspend/
  POST      /api/v1/owner/employees/:id/reactivate/

Operative auth endpoint (public — no Membership required):
  POST      /api/v1/auth/employee-login/
"""
from __future__ import annotations

import logging
import secrets
import string
from datetime import timedelta
from typing import Dict

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.backends import TokenBackend

from django.conf import settings

from apps.accounts.access import resolve_request_membership
from apps.accounts.authentication import EmployeeTokenAuthentication, EmployeeScopedThrottle
from apps.accounts.models import AccessAuditLog, EmployeeProfile
from apps.accounts.permissions import HasBusinessMembership, EmployeeIsAuthenticated
from apps.accounts.employee_serializers import (
    CreateEmployeeSerializer,
    EmployeeLoginSerializer,
    EmployeeProfileSerializer,
    ResetPinSerializer,
    UpdateEmployeeSerializer,
)
from apps.accounts.operative_permissions import employee_permissions_summary
from apps.business.context import build_business_context

logger = logging.getLogger(__name__)


# ── Timing-safe dummy hash (module-level constant) ────────────────────────────
# Used to keep hash-check cost constant when an employee or business is not
# found, preventing timing-oracle attacks that otherwise reveal account existence.
from django.contrib.auth.hashers import make_password as _make_password_for_dummy
_DUMMY_HASH: str = _make_password_for_dummy('000000TIMING_GUARD_XXXXXXXX')


# ── Authorization helpers ─────────────────────────────────────────────────────

def _can_manage_employees(membership) -> bool:
    """Owner and admin can manage employees."""
    return membership and membership.role in ('owner', 'admin')


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_user_agent(request: Request) -> str:
    return request.META.get('HTTP_USER_AGENT', '')[:500]


# ── Audit helper for employee actions ────────────────────────────────────────

def _audit_employee(
    action: str,
    actor_membership,
    employee: EmployeeProfile,
    request: Request,
    details: Dict = None,
    before_json: Dict = None,
    after_json: Dict = None,
) -> None:
    """Create an AccessAuditLog entry for an employee-related action."""
    actor_user = actor_membership.user if actor_membership else None
    AccessAuditLog.objects.create(
        action=action,
        actor=actor_user,
        target_user=None,               # no direct User target for employee actions
        business=employee.business,
        details=details or {},
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
        actor_type=AccessAuditLog.ActorType.USER,
        entity_type='employee_profile',
        entity_id=str(employee.pk),
        before_json=before_json,
        after_json=after_json,
    )


# ── Code generation ───────────────────────────────────────────────────────────

def _generate_employee_code(business) -> str:
    """Generate a unique EMP-NNNN code for the given business."""
    existing = set(
        EmployeeProfile.objects.filter(business=business)
        .values_list('employee_code', flat=True)
    )
    for seq in range(1, 10_000):
        code = f'EMP-{seq:04d}'
        if code not in existing:
            return code
    # Extremely unlikely; generate a random suffix as last resort
    suffix = secrets.token_hex(3).upper()
    return f'EMP-{suffix}'


def _generate_temporary_pin(length: int = 6) -> str:
    """Generate a random numeric PIN."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def _employee_snapshot(employee: EmployeeProfile) -> Dict:
    """Return a JSON-safe snapshot of key employee fields for audit diff."""
    return {
        'first_name':      employee.first_name,
        'last_name':       employee.last_name,
        'alias':           employee.alias,
        'role_type':       employee.role_type,
        'credential_type': employee.credential_type,
        'status':          employee.status,
        'must_change_pin': employee.must_change_pin,
        'branch':          employee.branch_id,
    }


# ── List + Create ─────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def employees_list(request: Request) -> Response:
    """
    GET  /api/v1/owner/employees/  → list all employees in the business
    POST /api/v1/owner/employees/  → create a new operative employee
    """
    membership = resolve_request_membership(request)
    if not membership:
        return Response({'error': 'Sin membresía activa.'}, status=status.HTTP_403_FORBIDDEN)

    if not _can_manage_employees(membership):
        return Response(
            {'error': 'Solo el Owner o Admin pueden gestionar empleados.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    business = membership.business
    # Resolve HQ for family-wide employee listing
    hq = business.parent if getattr(business, 'parent', None) else business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    if request.method == 'GET':
        qs = (
            EmployeeProfile.objects
            .filter(business__id__in=family_ids)
            .select_related('business', 'branch', 'created_by_membership__user')
            .order_by('status', 'last_name', 'first_name')
        )
        return Response(EmployeeProfileSerializer(qs, many=True).data)

    # ── POST ─────────────────────────────────────────────────────────────────
    serializer = CreateEmployeeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # Resolve / validate branch
    branch = None
    branch_id = data.get('branch')
    if branch_id:
        from apps.business.models import Business as BizModel
        try:
            branch = BizModel.objects.get(pk=branch_id)
            if branch.id not in family_ids:
                return Response(
                    {'error': 'La sucursal no pertenece a este negocio.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except BizModel.DoesNotExist:
            return Response({'error': 'Sucursal no encontrada.'}, status=status.HTTP_400_BAD_REQUEST)

    # Resolve employee_code
    code = data.get('employee_code') or _generate_employee_code(hq)

    # Uniqueness per business
    if EmployeeProfile.objects.filter(business=hq, employee_code=code).exists():
        return Response(
            {'error': f'El código {code} ya está en uso para este negocio.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Handle PIN
    raw_pin = data.get('initial_pin') or ''
    if not raw_pin:
        raw_pin = _generate_temporary_pin()
        temp_pin_generated = True
    else:
        temp_pin_generated = False

    pin_hash = make_password(raw_pin)

    with transaction.atomic():
        employee = EmployeeProfile.objects.create(
            business=hq,
            branch=branch,
            first_name=data['first_name'],
            last_name=data['last_name'],
            alias=data.get('alias', ''),
            employee_code=code,
            role_type=data['role_type'],
            credential_type=data.get('credential_type', EmployeeProfile.CredentialType.PIN),
            login_code_hash=pin_hash,
            must_change_pin=False,
            status=EmployeeProfile.Status.ACTIVE,
            created_by_membership=membership,
        )

        _audit_employee(
            action='EMPLOYEE_CREATED',
            actor_membership=membership,
            employee=employee,
            request=request,
            details={
                'employee_code': employee.employee_code,
                'role_type': employee.role_type,
            },
            after_json=_employee_snapshot(employee),
        )

    logger.info(
        '[employee_views] EMPLOYEE_CREATED employee=%s code=%s business=%s by=%s',
        employee.pk, employee.employee_code, hq.pk, membership.user.pk,
    )

    response_data = EmployeeProfileSerializer(employee).data
    # Return the PIN once (plain text) so the admin can hand it to the employee.
    response_data['initial_pin'] = raw_pin
    response_data['pin_was_generated'] = temp_pin_generated
    # Ensure business_code is always included for the credential sheet.
    if 'business_code' not in response_data or not response_data['business_code']:
        response_data['business_code'] = hq.slug

    return Response(response_data, status=status.HTTP_201_CREATED)


# ── Detail + Update ───────────────────────────────────────────────────────────

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def employee_detail(request: Request, employee_id) -> Response:
    """
    GET  /api/v1/owner/employees/:id/ → detail
    PATCH /api/v1/owner/employees/:id/ → editar
    """
    membership = resolve_request_membership(request)
    if not membership:
        return Response({'error': 'Sin membresía activa.'}, status=status.HTTP_403_FORBIDDEN)

    if not _can_manage_employees(membership):
        return Response(
            {'error': 'Solo el Owner o Admin pueden gestionar empleados.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    hq = membership.business.parent if getattr(membership.business, 'parent', None) else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    try:
        employee = EmployeeProfile.objects.select_related(
            'business', 'branch', 'created_by_membership__user'
        ).get(pk=employee_id, business__id__in=family_ids)
    except (EmployeeProfile.DoesNotExist, ValueError):
        return Response({'error': 'Empleado no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(EmployeeProfileSerializer(employee).data)

    # ── PATCH ─────────────────────────────────────────────────────────────────
    serializer = UpdateEmployeeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    before = _employee_snapshot(employee)
    changed_fields = []

    # Validate branch if provided
    new_branch_id = data.get('branch', '$MISSING')
    if new_branch_id != '$MISSING':
        if new_branch_id is None:
            employee.branch = None
            changed_fields.append('branch')
        else:
            from apps.business.models import Business as BizModel
            try:
                new_branch = BizModel.objects.get(pk=new_branch_id)
                if new_branch.id not in family_ids:
                    return Response({'error': 'La sucursal no pertenece a este negocio.'}, status=400)
                employee.branch = new_branch
                changed_fields.append('branch')
            except BizModel.DoesNotExist:
                return Response({'error': 'Sucursal no encontrada.'}, status=400)

    old_role = employee.role_type
    for field in ('first_name', 'last_name', 'alias', 'role_type', 'credential_type'):
        if field in data:
            setattr(employee, field, data[field])
            changed_fields.append(field)

    if not changed_fields:
        return Response(EmployeeProfileSerializer(employee).data)

    with transaction.atomic():
        employee.updated_by_membership = membership
        employee.save(update_fields=changed_fields + ['updated_by_membership', 'updated_at'])

        action = 'ROLE_CHANGED' if 'role_type' in changed_fields else 'EMPLOYEE_UPDATED'
        details = {'changed_fields': changed_fields}
        if 'role_type' in changed_fields:
            details['old_role'] = old_role
            details['new_role'] = employee.role_type

        _audit_employee(
            action=action,
            actor_membership=membership,
            employee=employee,
            request=request,
            details=details,
            before_json=before,
            after_json=_employee_snapshot(employee),
        )

    return Response(EmployeeProfileSerializer(employee).data)


# ── Reset PIN ─────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def employee_reset_pin(request: Request, employee_id) -> Response:
    """
    POST /api/v1/owner/employees/:id/reset-pin/

    Resets the employee's PIN/credential.  If 'new_pin' is provided in the
    request body it is used; otherwise a random 6-digit PIN is generated.
    Returns the plain-text PIN once (never stored, never returned again).
    """
    membership = resolve_request_membership(request)
    if not membership or not _can_manage_employees(membership):
        return Response({'error': 'Sin permisos para resetear PIN.'}, status=status.HTTP_403_FORBIDDEN)

    hq = membership.business.parent if getattr(membership.business, 'parent', None) else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    try:
        employee = EmployeeProfile.objects.get(pk=employee_id, business__id__in=family_ids)
    except (EmployeeProfile.DoesNotExist, ValueError):
        return Response({'error': 'Empleado no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ResetPinSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    raw_pin = serializer.validated_data.get('new_pin') or ''
    pin_was_generated = False
    if not raw_pin:
        raw_pin = _generate_temporary_pin()
        pin_was_generated = True

    with transaction.atomic():
        employee.login_code_hash = make_password(raw_pin)
        employee.must_change_pin = False
        employee.save(update_fields=['login_code_hash', 'must_change_pin', 'updated_at'])

        _audit_employee(
            action='PIN_RESET',
            actor_membership=membership,
            employee=employee,
            request=request,
            details={'pin_was_generated': pin_was_generated},
        )

    logger.info(
        '[employee_views] PIN_RESET employee=%s by=%s',
        employee.pk, membership.user.pk,
    )

    return Response({
        'success': True,
        'message': 'PIN reseteado. Entregá este código al empleado; no volverá a mostrarse.',
        'employee_code': employee.employee_code,
        'temporary_pin': raw_pin,
        'must_change_pin': False,
        'pin_was_generated': pin_was_generated,
    })


# ── Suspend / Reactivate ──────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def employee_suspend(request: Request, employee_id) -> Response:
    """POST /api/v1/owner/employees/:id/suspend/"""
    return _set_employee_status(
        request, employee_id,
        target_status=EmployeeProfile.Status.SUSPENDED,
        audit_action='EMPLOYEE_SUSPENDED',
        success_msg='Empleado suspendido.',
        already_msg='El empleado ya está suspendido.',
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBusinessMembership])
def employee_reactivate(request: Request, employee_id) -> Response:
    """POST /api/v1/owner/employees/:id/reactivate/"""
    return _set_employee_status(
        request, employee_id,
        target_status=EmployeeProfile.Status.ACTIVE,
        audit_action='EMPLOYEE_REACTIVATED',
        success_msg='Empleado reactivado.',
        already_msg='El empleado ya está activo.',
    )


def _set_employee_status(
    request: Request,
    employee_id,
    target_status: str,
    audit_action: str,
    success_msg: str,
    already_msg: str,
) -> Response:
    membership = resolve_request_membership(request)
    if not membership or not _can_manage_employees(membership):
        return Response({'error': 'Sin permisos.'}, status=status.HTTP_403_FORBIDDEN)

    hq = membership.business.parent if getattr(membership.business, 'parent', None) else membership.business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    try:
        employee = EmployeeProfile.objects.get(pk=employee_id, business__id__in=family_ids)
    except (EmployeeProfile.DoesNotExist, ValueError):
        return Response({'error': 'Empleado no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    if employee.status == target_status:
        return Response({'message': already_msg, 'status': employee.status})

    before = _employee_snapshot(employee)

    with transaction.atomic():
        employee.status = target_status
        employee.updated_by_membership = membership
        employee.save(update_fields=['status', 'updated_by_membership', 'updated_at'])

        _audit_employee(
            action=audit_action,
            actor_membership=membership,
            employee=employee,
            request=request,
            details={'new_status': target_status},
            before_json=before,
            after_json=_employee_snapshot(employee),
        )

    return Response({
        'success': True,
        'message': success_msg,
        'id': str(employee.pk),
        'status': employee.status,
        'status_display': employee.get_status_display(),
    })


# ── Operative login ───────────────────────────────────────────────────────────

class EmployeeLoginView(APIView):
    """
    POST /api/v1/auth/employee-login/

    Validates operative credentials (business_id + employee_code + PIN) and
    returns a short-lived signed JWT with employee claims.

    The token is intended for use in X-Employee-Token requests from POS
    terminals.  It is NOT set as a cookie — clients store it explicitly.

    Response on success:
    {
        "token": "<jwt>",
        "actor_type": "employee",
        "employee_id": "<uuid>",
        "employee_code": "EMP-0001",
        "display_name": "Ana García",
        "business_id": 1,
        "business_name": "Mi Negocio",
        "role_type": "cashier",
        "must_change_pin": false,
        "permissions": {"view_sales": true, ...}
    }
    """
    authentication_classes = []   # no auth required — this IS the auth
    permission_classes = []
    throttle_classes = [EmployeeScopedThrottle]
    throttle_scope = 'employee_login'

    def post(self, request: Request) -> Response:
        serializer = EmployeeLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        business_code = serializer.validated_data['business_code'].strip().lower()
        employee_code = serializer.validated_data['employee_code'].strip().upper()
        raw_pin       = serializer.validated_data['pin']

        # Resolve the business by slug
        from apps.business.models import Business as BizModel
        try:
            business = BizModel.objects.get(slug=business_code)
        except BizModel.DoesNotExist:
            # Timing mitigation: do a dummy hash check to equalise response time
            check_password(raw_pin, _DUMMY_HASH)
            return self._auth_failed(request, business_code, employee_code)

        # Resolve the employee
        try:
            employee = EmployeeProfile.objects.select_related('business').get(
                business=business,
                employee_code=employee_code,
            )
        except EmployeeProfile.DoesNotExist:
            # Timing mitigation: do a dummy hash check to equalise response time
            check_password(raw_pin, _DUMMY_HASH)
            return self._auth_failed(request, business_code, employee_code)

        # Status check
        if employee.status != EmployeeProfile.Status.ACTIVE:
            logger.warning(
                '[employee_login] Blocked inactive employee=%s status=%s business=%s',
                employee.pk, employee.status, business.pk,
            )
            return Response(
                {'error': 'Cuenta de empleado suspendida o inactiva.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Credential validation
        if not check_password(raw_pin, employee.login_code_hash):
            return self._auth_failed(request, business_code, employee_code, employee=employee)

        # Resolve permissions
        context = build_business_context(business)
        service = context.get('service', 'gestion')
        permissions = employee_permissions_summary(employee, service)

        # Generate employee JWT
        token = self._generate_employee_token(employee, business)

        # Audit login
        try:
            AccessAuditLog.objects.create(
                action='OPERATOR_SESSION_STARTED',
                actor=None,
                target_user=None,
                business=business,
                details={
                    'employee_code': employee.employee_code,
                    'role_type': employee.role_type,
                },
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                actor_type=AccessAuditLog.ActorType.EMPLOYEE,
                actor_employee=employee,
                entity_type='employee_profile',
                entity_id=str(employee.pk),
            )
        except Exception:
            logger.exception('[employee_login] Audit log failed for employee=%s', employee.pk)

        display_name = employee.alias or f'{employee.first_name} {employee.last_name}'.strip()

        return Response({
            'token':           token,
            'actor_type':      'employee',
            'employee_id':     str(employee.pk),
            'employee_code':   employee.employee_code,
            'display_name':    display_name,
            'business_id':     business.pk,
            'business_name':   business.name,
            'role_type':       employee.role_type,
            'must_change_pin': employee.must_change_pin,
            'permissions':     permissions,
        })

    def _auth_failed(self, request, business_code, employee_code, employee=None) -> Response:
        """Log a failed login attempt and return a generic error."""
        logger.warning(
            '[employee_login] FAILED business=%s code=%s ip=%s',
            business_code, employee_code, _get_client_ip(request),
        )
        if employee:
            try:
                AccessAuditLog.objects.create(
                    action='LOGIN_FAILED',
                    actor=None,
                    target_user=None,
                    business=employee.business,
                    details={'employee_code': employee_code, 'reason': 'bad_credentials'},
                    ip_address=_get_client_ip(request),
                    user_agent=_get_user_agent(request),
                    actor_type=AccessAuditLog.ActorType.EMPLOYEE,
                    actor_employee=employee,
                    entity_type='employee_profile',
                    entity_id=str(employee.pk),
                )
            except Exception:
                pass
        return Response(
            {'error': 'Credenciales incorrectas.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    @staticmethod
    def _generate_employee_token(employee: EmployeeProfile, business) -> str:
        """Generate a short-lived signed JWT with employee claims."""
        now = timezone.now()
        # 12-hour lifetime for operative sessions
        exp = now + timedelta(hours=12)

        payload = {
            'actor_type':   'employee',
            'employee_id':  str(employee.pk),
            'business_id':  business.pk,
            'role_type':    employee.role_type,
            'iat':          int(now.timestamp()),
            'exp':          int(exp.timestamp()),
        }

        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        return backend.encode(payload)


# ── Employee self-service PIN change ──────────────────────────────────────────


class EmployeeChangePinView(APIView):
    """
    POST /api/v1/auth/employee-change-pin/

    DISABLED — Self-service PIN change is no longer available for operative
    employees.  PINs are managed exclusively by the business owner/admin
    via the dashboard (reset-pin endpoint).

    This endpoint is kept registered to return a clear 403 error instead of
    a confusing 404 for any client still referencing it.
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated]
    throttle_classes = [EmployeeScopedThrottle]
    throttle_scope = 'employee_change_pin'

    def post(self, request: Request) -> Response:
        return Response(
            {
                'error': 'El cambio de PIN por parte del empleado no está habilitado. '
                         'Contacte al administrador del negocio.',
                'code': 'pin_change_disabled',
            },
            status=status.HTTP_403_FORBIDDEN,
        )
