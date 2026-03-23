from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.models import Membership, AccountProfile, AccessAuditLog
from apps.accounts.rbac import SERVICE_ROLE_PERMISSIONS
from apps.business.models import Business, Subscription

import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class LastOwnerProtectionError(ValidationError):
    """Raised when an operation would remove the last active owner from a business."""
    pass


class OwnerGuardService:
    """
    Enforces the invariant: every business HQ must always have at least one
    active owner Membership.

    Uses SELECT FOR UPDATE to prevent race conditions in concurrent requests.
    Must always be called inside a transaction.atomic() block.
    """

    @staticmethod
    def active_owner_count_excluding(business: Business, user) -> int:
        """
        Count active owner memberships in the business HQ family,
        excluding the given user.
        """
        hq = business.parent if business.parent else business
        family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
        return (
            Membership.objects
            .select_for_update()
            .filter(
                business__id__in=family_ids,
                role='owner',
                status=Membership.Status.ACTIVE,
            )
            .exclude(user=user)
            .count()
        )

    @classmethod
    def assert_not_last_owner(cls, business: Business, user) -> None:
        """
        Raise LastOwnerProtectionError if removing/disabling `user` from
        `business` would leave the business without any active owner.

        Only relevant when the target user currently has an owner role.
        Callers should call this only when the operation is relevant
        (e.g., before disabling an owner-role user).
        """
        target_membership = (
            Membership.objects
            .filter(business__in=[business.pk] + list(
                business.branches.values_list('id', flat=True)
            ) if not business.parent else [business.pk],
                    user=user, role='owner', status=Membership.Status.ACTIVE)
            .first()
        )
        if target_membership is None:
            # Target user is not an active owner — guard not applicable.
            return

        remaining_owners = cls.active_owner_count_excluding(business, user)
        if remaining_owners == 0:
            raise LastOwnerProtectionError(
                "No es posible eliminar, suspender o desactivar al último propietario (owner) "
                "del negocio. Asigna otro propietario antes de continuar."
            )


class EmailService:
    """
    Thin wrapper around Django's send_mail for transactional emails.
    All failures are logged but do NOT propagate — registration/reset flows
    should succeed even if the email server is temporarily unavailable.
    """

    @staticmethod
    def send_verification_email(user, token: str) -> bool:
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        verify_url = f"{frontend_url}/verificar-email?token={token}"
        subject = "Verificá tu email en Mirubro"
        body = (
            f"Hola,\n\n"
            f"Para activar tu cuenta en Mirubro, hacé clic en el siguiente enlace:\n\n"
            f"  {verify_url}\n\n"
            f"Este enlace es válido por {getattr(settings, 'EMAIL_VERIFICATION_TOKEN_HOURS', 48)} horas.\n\n"
            f"Si no creaste una cuenta, ignorá este mensaje.\n\n"
            f"— El equipo de Mirubro"
        )
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception(
                "[EmailService] Failed to send verification email to user=%s", user.pk
            )
            return False

    @staticmethod
    def send_password_reset_email(user, token: str) -> bool:
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        reset_url = f"{frontend_url}/nueva-contrasena?token={token}"
        subject = "Recuperá tu contraseña en Mirubro"
        hours = getattr(settings, 'PASSWORD_RESET_TOKEN_HOURS', 2)
        body = (
            f"Hola,\n\n"
            f"Recibimos una solicitud para restablecer tu contraseña en Mirubro.\n\n"
            f"Hacé clic en el siguiente enlace para continuar:\n\n"
            f"  {reset_url}\n\n"
            f"Este enlace es válido por {hours} hora{'s' if hours != 1 else ''}.\n\n"
            f"Si no solicitaste este cambio, ignorá este mensaje. Tu contraseña no será modificada.\n\n"
            f"— El equipo de Mirubro"
        )
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception(
                "[EmailService] Failed to send password-reset email to user=%s", user.pk
            )
            return False


class MembershipService:
    @staticmethod
    def create_membership_safely(user, business, role):
        """
        Creates a membership ensuring seat limits are respected with row locking.
        """
        with transaction.atomic():
            # Resolve HQ and lock specific tables or rows if possible
            # We lock the HQ business to serialize additions to the family
            hq = business.parent if business.parent else business
            
            # Select for update to prevent concurrent reads of seat counts
            # We lock the HQ subscription since the limit is there
            try:
                sub = Subscription.objects.select_for_update().get(business=hq)
            except Subscription.DoesNotExist:
                # If no subscription, maybe we don't enforce? Or fail?
                # Default logic usually implies open or starter. 
                # Assuming check_seat_limit signal default behavior: if no sub, no limit.
                sub = None

            if sub and sub.max_seats > 0:
                family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
                current_count = Membership.objects.filter(business__id__in=family_ids).count()
                
                if current_count >= sub.max_seats:
                    raise ValidationError(f"Límite de usuarios ({sub.max_seats}) alcanzado para la cuenta {hq.name}.")

            # Proceed to create
            return Membership.objects.create(user=user, business=business, role=role)


class InternalUserService:
    """
    Creates internal users directly (by the owner), without registration,
    email verification or onboarding flow.

    Transactional: User + AccountProfile + Membership created atomically.
    Enforces seat limits and role validation.
    """

    # Roles that can be assigned via this endpoint.
    # Owner creation is disallowed by default to prevent privilege escalation.
    DISALLOWED_ROLES = {'owner'}

    @classmethod
    def create_internal_user(
        cls,
        *,
        business: Business,
        first_name: str,
        last_name: str,
        username: str,
        password: str,
        role: str,
        email: str = '',
        created_by_user=None,
        request=None,
    ) -> dict:
        """
        Create an internal user with a membership in the given business.

        Returns dict with 'user' and 'membership' keys.

        Raises ValidationError on constraint violations.
        """
        # ── Validate role ──────────────────────────────────────────────
        if role in cls.DISALLOWED_ROLES:
            raise ValidationError(
                f'No se permite crear usuarios con el rol "{role}" desde este flujo.'
            )

        service_type = getattr(business, 'service_type', None) or getattr(business, 'default_service', None) or 'gestion'
        service_roles = SERVICE_ROLE_PERMISSIONS.get(service_type, {})
        if role not in service_roles:
            valid = ', '.join(sorted(service_roles.keys() - cls.DISALLOWED_ROLES))
            raise ValidationError(
                f'El rol "{role}" no es válido para el servicio "{service_type}". '
                f'Opciones: {valid}'
            )

        # ── Validate username uniqueness ───────────────────────────────
        username = username.strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                f'El nombre de usuario "{username}" ya está en uso.'
            )

        # ── Validate email uniqueness (if provided) ───────────────────
        email = (email or '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                f'El email "{email}" ya está registrado en otra cuenta.'
            )

        # ── Transactional creation ─────────────────────────────────────
        with transaction.atomic():
            # Seat limit check (lock HQ subscription row)
            hq = business.parent if business.parent else business
            try:
                sub = Subscription.objects.select_for_update().get(business=hq)
            except Subscription.DoesNotExist:
                sub = None

            if sub and sub.max_seats > 0:
                family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
                current_count = Membership.objects.filter(
                    business__id__in=family_ids,
                ).count()
                if current_count >= sub.max_seats:
                    raise ValidationError(
                        f'Límite de usuarios ({sub.max_seats}) alcanzado para "{hq.name}". '
                        f'Mejora tu plan para agregar más usuarios.'
                    )

            # Create Django User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
            )

            # AccountProfile is auto-created by post_save signal.
            # Mark as active + email_verified for internal users (no verification flow).
            AccountProfile.objects.filter(user=user).update(
                account_status=AccountProfile.AccountStatus.ACTIVE,
                email_verified=True,
            )

            # Create Membership
            membership = Membership.objects.create(
                user=user,
                business=business,
                role=role,
                status=Membership.Status.ACTIVE,
                created_by_user=created_by_user,
            )

            # Audit log
            ip_address = None
            user_agent = ''
            if request:
                xff = request.META.get('HTTP_X_FORWARDED_FOR')
                ip_address = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

            AccessAuditLog.objects.create(
                action='USER_CREATED',
                actor=created_by_user,
                target_user=user,
                business=business,
                actor_type=AccessAuditLog.ActorType.USER,
                entity_type='membership',
                entity_id=str(membership.pk),
                details={
                    'username': username,
                    'role': role,
                    'email': email or None,
                    'created_by': created_by_user.pk if created_by_user else None,
                },
                after_json={
                    'user_id': user.pk,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': role,
                    'membership_status': Membership.Status.ACTIVE,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )

            logger.info(
                "[InternalUserService] Created internal user=%s username=%s "
                "role=%s business=%s by owner=%s",
                user.pk, username, role, business.pk,
                created_by_user.pk if created_by_user else None,
            )

            return {'user': user, 'membership': membership}

