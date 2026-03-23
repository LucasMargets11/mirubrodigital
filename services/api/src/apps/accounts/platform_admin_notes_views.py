"""
Platform admin views — Internal Notes (observations).

Allows platform staff to create and list internal notes attached to any entity.
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.admin_internal_note import AdminInternalNote
from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action

ALLOWED_TARGET_TYPES = {'business', 'subscription_v2'}
MAX_BODY_LENGTH = 2000


class AdminInternalNoteListCreateView(APIView):
    """
    GET  /api/v1/platform-admin/notes/?target_type=business&target_id=42
    POST /api/v1/platform-admin/notes/
         { "target_type": "business", "target_id": "42", "body": "..." }
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        target_type = request.query_params.get('target_type', '').strip()
        target_id = request.query_params.get('target_id', '').strip()

        if target_type not in ALLOWED_TARGET_TYPES or not target_id:
            return Response({'detail': 'target_type y target_id son requeridos.'}, status=400)

        notes = (
            AdminInternalNote.objects
            .filter(target_type=target_type, target_id=target_id)
            .select_related('author')
            .order_by('-created_at')[:50]
        )

        return Response({
            'results': [
                {
                    'id': str(n.id),
                    'body': n.body,
                    'author_email': n.author.email if n.author else 'Sistema',
                    'author_name': n.author.get_full_name() if n.author else 'Sistema',
                    'created_at': n.created_at.isoformat() if n.created_at else None,
                }
                for n in notes
            ]
        })

    def post(self, request: Request) -> Response:
        target_type = (request.data.get('target_type') or '').strip()
        target_id = (request.data.get('target_id') or '').strip()
        body = (request.data.get('body') or '').strip()

        if target_type not in ALLOWED_TARGET_TYPES:
            return Response({'detail': f'target_type inválido. Opciones: {", ".join(sorted(ALLOWED_TARGET_TYPES))}'}, status=400)
        if not target_id:
            return Response({'detail': 'target_id es requerido.'}, status=400)
        if not body:
            return Response({'detail': 'body es requerido.'}, status=400)
        if len(body) > MAX_BODY_LENGTH:
            return Response({'detail': f'body demasiado largo (máx {MAX_BODY_LENGTH} caracteres).'}, status=400)

        # ── Validate target exists ────────────────────────────────────────
        business = None
        if target_type == 'business':
            from apps.business.models import Business
            business = Business.objects.filter(pk=target_id).first()
            if not business:
                return Response({'detail': 'El cliente (business) indicado no existe.'}, status=404)
        elif target_type == 'subscription_v2':
            from apps.billing.models import SubscriptionV2
            sub = SubscriptionV2.objects.filter(pk=target_id).select_related('business').first()
            if not sub:
                return Response({'detail': 'La suscripción indicada no existe.'}, status=404)
            business = sub.business

        note = AdminInternalNote.objects.create(
            target_type=target_type,
            target_id=target_id,
            body=body,
            author=request.user,
        )

        log_platform_action(
            action='ADMIN_NOTE_CREATED',
            actor=request.user,
            entity_type='admin_internal_note',
            entity_id=str(note.id),
            business=business,
            details={
                'target_type': target_type,
                'target_id': target_id,
            },
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({
            'id': str(note.id),
            'body': note.body,
            'author_email': request.user.email,
            'author_name': request.user.get_full_name() or request.user.get_username(),
            'created_at': note.created_at.isoformat() if note.created_at else None,
        }, status=201)
