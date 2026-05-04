"""
Platform Admin permissions for internal backoffice access.

These permission classes protect /api/v1/platform-admin/ endpoints.
They verify that the user is authenticated AND has is_platform_staff=True
on their AccountProfile, optionally restricting by internal_role.
"""
from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class IsPlatformStaff(BasePermission):
    """
    Allows access only to users marked as platform staff.
    """
    message = 'Acceso restringido a personal interno de Mi Rubro.'

    def has_permission(self, request: Request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        profile = getattr(user, 'account_profile', None)
        if profile is None:
            return False
        return profile.is_platform_staff


class HasInternalRole(BasePermission):
    """
    Restricts access to users with specific internal roles.

    Usage on a view::

        allowed_internal_roles = ['superadmin', 'operations']
        permission_classes = [IsPlatformStaff, HasInternalRole]
    """
    message = 'No tenés permisos para acceder a esta sección.'

    def has_permission(self, request: Request, view) -> bool:
        allowed = getattr(view, 'allowed_internal_roles', None)
        if not allowed:
            return True  # No role restriction specified → pass
        profile = getattr(request.user, 'account_profile', None)
        if profile is None:
            return False
        return profile.internal_role in allowed


# ── Role → authorized admin sections mapping ─────────────────────────────────
# Used by AdminNavigationView to return only the sections a user can access.

INTERNAL_ROLE_SECTIONS = {
    'superadmin': [
        'dashboard', 'clientes', 'suscripciones', 'soporte',
        'blog', 'reportes', 'configuracion', 'promociones',
    ],
    'operations': [
        'dashboard', 'clientes', 'suscripciones', 'reportes',
    ],
    'support_agent': [
        'dashboard', 'soporte',
    ],
    'content_admin': [
        'dashboard', 'blog',
    ],
}


def get_authorized_sections(internal_role: str) -> list[str]:
    """Return the admin sections a given internal role can access."""
    return INTERNAL_ROLE_SECTIONS.get(internal_role, [])
