import logging

from django.db import connection
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _check_db():
    """Return True if the default database is reachable."""
    try:
        connection.ensure_connection()
        return True
    except Exception:
        logger.warning('health: database unreachable', exc_info=True)
        return False


def _check_redis():
    """Return True if the default cache (Redis) is reachable."""
    try:
        cache.set('_health', '1', timeout=5)
        return cache.get('_health') == '1'
    except Exception:
        logger.warning('health: redis/cache unreachable', exc_info=True)
        return False


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([])
def health_check(_request):
    """Liveness / readiness probe for ALB / ECS / k8s.

    Returns 200 when all dependencies are reachable, 503 otherwise.
    Response body always includes per-dependency status so operators
    can quickly identify which backend is failing.
    """
    db_ok = _check_db()
    redis_ok = _check_redis()
    healthy = db_ok and redis_ok

    payload = {
        'status': 'ok' if healthy else 'degraded',
        'dependencies': {
            'database': 'ok' if db_ok else 'unavailable',
            'redis': 'ok' if redis_ok else 'unavailable',
        },
    }

    return Response(payload, status=200 if healthy else 503)
