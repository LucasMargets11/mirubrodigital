import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

_PLACEHOLDER_MARKERS = ('xxxx', 'placeholder', 'your_token', 'changeme', 'APP_USR-0000', 'TEST-0000')


def _looks_like_placeholder(value: str) -> bool:
    return any(m in value.lower() for m in _PLACEHOLDER_MARKERS)


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'

    def ready(self):
        """Emit startup warnings when Mercado Pago config is incomplete or placeholder."""
        from django.conf import settings

        token = getattr(settings, 'MP_ACCESS_TOKEN', None) or ''
        base_url = getattr(settings, 'BASE_PUBLIC_URL', None) or ''

        if not token:
            logger.warning(
                '[MercadoPago] MP_ACCESS_TOKEN is not set. '
                'The tip create-preference endpoint will return 503. '
                'Add a TEST token to services/api/.env'
            )
        elif _looks_like_placeholder(token):
            logger.warning(
                '[MercadoPago] MP_ACCESS_TOKEN looks like a placeholder (%s...). '
                'Replace it with a real TEST token from mercadopago.com → Credenciales de prueba.',
                token[:20],
            )

        if not base_url:
            logger.warning(
                '[MercadoPago] BASE_PUBLIC_URL is not set. '
                'MP webhook notifications will NOT arrive in DEV. '
                'Run: ngrok http 8000  and set BASE_PUBLIC_URL=https://<your-ngrok-url>.ngrok-free.app'
            )
        elif _looks_like_placeholder(base_url):
            logger.warning(
                '[MercadoPago] BASE_PUBLIC_URL still has a placeholder value (%s). '
                'Run `ngrok http 8000`, copy the HTTPS URL, and update BASE_PUBLIC_URL in services/api/.env',
                base_url,
            )
