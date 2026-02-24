"""
Servicios helper para acceso centralizado a configuración de negocio.
Provee métodos de conveniencia para obtener datos de emisor, branding y series.
"""
from typing import Dict, Optional, Any
from django.db import transaction

from .models import Business, BusinessBillingProfile, BusinessBranding
from apps.invoices.models import DocumentSeries


class BusinessDocumentConfig:
    """
    Contenedor de configuración de negocio para emisión de documentos.
    Provee acceso unificado a datos de emisor, branding y series.
    """
    
    def __init__(self, business: Business):
        self.business = business
        self._billing_profile: Optional[BusinessBillingProfile] = None
        self._branding: Optional[BusinessBranding] = None
        self._series_cache: Dict[str, DocumentSeries] = {}
    
    @property
    def billing_profile(self) -> BusinessBillingProfile:
        """Obtener perfil de facturación (lazy load, auto-crea si no existe)."""
        if self._billing_profile is None:
            self._billing_profile, _ = BusinessBillingProfile.objects.get_or_create(
                business=self.business
            )
        return self._billing_profile
    
    @property
    def branding(self) -> BusinessBranding:
        """Obtener branding (lazy load, auto-crea si no existe)."""
        if self._branding is None:
            self._branding, _ = BusinessBranding.objects.get_or_create(
                business=self.business
            )
        return self._branding
    
    def is_ready_to_emit(self) -> bool:
        """Verificar si el negocio tiene configuración completa para emitir."""
        return self.billing_profile.is_complete()
    
    def get_default_series(self, document_type: str) -> Optional[DocumentSeries]:
        """
        Obtener serie predeterminada para un tipo de documento.
        
        Args:
            document_type: Tipo de documento ('invoice', 'quote', etc.)
        
        Returns:
            DocumentSeries o None si no hay serie por defecto
        """
        cache_key = f"default_{document_type}"
        if cache_key not in self._series_cache:
            self._series_cache[cache_key] = DocumentSeries.objects.filter(
                business=self.business,
                document_type=document_type,
                is_default=True,
                is_active=True
            ).first()
        return self._series_cache[cache_key]
    
    def get_series_by_letter(self, document_type: str, letter: str) -> Optional[DocumentSeries]:
        """
        Obtener serie específica por tipo de documento y letra.
        
        Args:
            document_type: Tipo de documento
            letter: Letra del comprobante ('A', 'B', 'C', etc.)
        
        Returns:
            DocumentSeries o None si no existe
        """
        cache_key = f"{document_type}_{letter}"
        if cache_key not in self._series_cache:
            self._series_cache[cache_key] = DocumentSeries.objects.filter(
                business=self.business,
                document_type=document_type,
                letter=letter,
                is_active=True
            ).first()
        return self._series_cache[cache_key]
    
    def get_issuer_data(self) -> Dict[str, Any]:
        """
        Obtener datos del emisor formateados para uso en PDFs y documentos.
        Robusto: usa getattr para todos los campos; nunca lanza AttributeError
        aunque el modelo no tenga algún campo opcional.
        El campo 'legal_address' expone fiscal_address (fuente real del modelo)
        con fallback a commercial_address para compatibilidad.

        Returns:
            Dict con datos del emisor:
            {
                'legal_name': str,
                'trade_name': str,
                'tax_id': str,
                'tax_id_type': str,
                'tax_id_display': str (formateado),
                'vat_condition': str,
                'vat_condition_display': str,
                'fiscal_address': str  (campo real del modelo),
                'legal_address': str   (alias de fiscal_address para compatibilidad PDF),
                'commercial_address': str,
                'city': str,
                'state_province': str,
                'postal_code': str,
                'country': str,
                'phone': str,
                'email': str,
                'website': str,
                'iibb': str,
                'activity_start_date': date or None,
            }
        """
        profile = self.billing_profile

        # Domicilios — el modelo tiene fiscal_address y commercial_address.
        # legal_address es un alias para compatibilidad con el PDF.
        fiscal_address = getattr(profile, 'fiscal_address', '') or ''
        # Por si en una migración futura se agrega legal_address al modelo:
        _model_legal_address = getattr(profile, 'legal_address', '') or ''
        legal_address = _model_legal_address or fiscal_address
        commercial_address = getattr(profile, 'commercial_address', '') or legal_address

        # Identificación fiscal
        tax_id = getattr(profile, 'tax_id', '') or ''
        tax_id_display = ''
        if tax_id:
            try:
                tax_id_display = f"{profile.get_tax_id_type_display()}: {tax_id}"
            except Exception:
                tax_id_display = tax_id

        # Condición IVA
        vat_condition = getattr(profile, 'vat_condition', '') or ''
        vat_condition_display = ''
        try:
            vat_condition_display = profile.get_vat_condition_display() or ''
        except Exception:
            vat_condition_display = vat_condition

        return {
            'legal_name': getattr(profile, 'legal_name', '') or '',
            'trade_name': getattr(profile, 'trade_name', '') or '',
            'tax_id': tax_id,
            'tax_id_type': getattr(profile, 'tax_id_type', '') or '',
            'tax_id_display': tax_id_display,
            'vat_condition': vat_condition,
            'vat_condition_display': vat_condition_display,
            'fiscal_address': fiscal_address,
            'legal_address': legal_address,
            'commercial_address': commercial_address,
            # Campos opcionales que el modelo puede no tener aún:
            'city': getattr(profile, 'city', '') or '',
            'state_province': getattr(profile, 'state_province', '') or '',
            'postal_code': getattr(profile, 'postal_code', '') or '',
            'country': getattr(profile, 'country', '') or '',
            'phone': getattr(profile, 'phone', '') or '',
            'email': getattr(profile, 'email', '') or '',
            'website': getattr(profile, 'website', '') or '',
            'iibb': getattr(profile, 'iibb', '') or '',
            'activity_start_date': getattr(profile, 'activity_start_date', None),
        }

    def get_missing_issuer_fields(self) -> list:
        """
        Retorna lista de claves de campos obligatorios que están vacíos en el perfil de emisor.
        Usado para devolver 422 con detalle antes de generar PDF.

        Returns:
            Lista de strings con nombres de campos faltantes. Lista vacía = perfil completo.
        """
        profile = self.billing_profile
        missing = []

        if not (getattr(profile, 'legal_name', '') or '').strip():
            missing.append('legal_name')

        fiscal_address = (getattr(profile, 'fiscal_address', '') or '').strip()
        commercial_address = (getattr(profile, 'commercial_address', '') or '').strip()
        if not fiscal_address and not commercial_address:
            missing.append('fiscal_address')

        return missing

    def get_branding_data(self) -> Dict[str, Any]:
        """
        Obtener datos de branding formateados.
        
        Returns:
            Dict con datos de branding:
            {
                'logo_horizontal': ImageFieldFile o None,
                'logo_square': ImageFieldFile o None,
                'accent_color': str (hex),
            }
        """
        branding = self.branding
        return {
            'logo_horizontal': getattr(branding, 'logo_horizontal', None) or None,
            'logo_square': getattr(branding, 'logo_square', None) or None,
            'accent_color': getattr(branding, 'accent_color', '') or '#0f172a',
        }

    def get_invoice_branding(self) -> Dict[str, Any]:
        """
        Obtener datos de branding específicos para facturas PDF.
        Nunca lanza excepción; fallbacks seguros para todos los campos.

        Returns:
            Dict:
            {
                'logo_header': ImageFieldFile o None  (logo_horizontal, fallback logo_square),
                'logo_horizontal': ImageFieldFile o None,
                'logo_square': ImageFieldFile o None,
                'accent_color': str (hex),
            }
        """
        try:
            branding = self.branding
            logo_horizontal = getattr(branding, 'logo_horizontal', None) or None
            logo_square = getattr(branding, 'logo_square', None) or None
            # "logo_header" usa horizontal de preferencia, fallback al cuadrado
            logo_header = logo_horizontal or logo_square
            return {
                'logo_header': logo_header,
                'logo_horizontal': logo_horizontal,
                'logo_square': logo_square,
                'accent_color': getattr(branding, 'accent_color', '') or '#0f172a',
            }
        except Exception:
            return {
                'logo_header': None,
                'logo_horizontal': None,
                'logo_square': None,
                'accent_color': '#0f172a',
            }


def get_business_document_config(business: Business) -> BusinessDocumentConfig:
    """
    Obtener config de documento para un negocio.
    
    Args:
        business: Instancia de Business
    
    Returns:
        BusinessDocumentConfig con datos cargados
    """
    return BusinessDocumentConfig(business)


def get_next_document_number(series_id: str) -> str:
    """
    Obtener el próximo número de documento de una serie de forma atómica.
    
    Args:
        series_id: UUID de la serie de documento
    
    Returns:
        Número completo formateado (ej: "0001-00000123")
    
    Raises:
        DocumentSeries.DoesNotExist: Si la serie no existe
    """
    with transaction.atomic():
        series = DocumentSeries.objects.select_for_update().get(pk=series_id)
        return series.get_next_number()
