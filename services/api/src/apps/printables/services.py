"""
Servicios auxiliares para el módulo Printables.

- resolve_signage_logo: resuelve el campo de logo según logo_variant,
  nunca lanza excepciones.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_signage_logo(business, logo_variant: str):
    """
    Devuelve el ImageFieldFile del logo a usar según logo_variant,
    o None si no hay logo disponible o variant es 'none'.

    Nunca lanza excepciones — cualquier error retorna None.

    En producción con S3, resolve_document_logo_path() maneja correctamente
    el caso NotImplementedError usando storage.open() + BytesIO, por lo que
    el logo se renderiza sin problemas tanto en local como en S3.
    """
    if logo_variant == 'none':
        return None

    try:
        from apps.business.services import get_business_document_config
        config = get_business_document_config(business)
        branding_data = config.get_invoice_branding()

        if logo_variant == 'horizontal':
            field = branding_data.get('logo_horizontal')
        elif logo_variant == 'square':
            field = branding_data.get('logo_square')
        else:
            # 'default': horizontal primero, luego square
            field = branding_data.get('logo_horizontal') or branding_data.get('logo_square')

        if not field:
            return None

        # Verificar que el campo tiene archivo asignado
        if not field.name:
            return None

        return field

    except Exception:
        logger.warning(
            'resolve_signage_logo: no se pudo resolver el logo (business=%s, variant=%s)',
            getattr(business, 'id', '?'),
            logo_variant,
            exc_info=True,
        )
        return None
