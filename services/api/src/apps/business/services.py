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
        """Obtener perfil de facturación (lazy load)."""
        if self._billing_profile is None:
            self._billing_profile = BusinessBillingProfile.objects.get(business=self.business)
        return self._billing_profile
    
    @property
    def branding(self) -> BusinessBranding:
        """Obtener branding (lazy load)."""
        if self._branding is None:
            self._branding = BusinessBranding.objects.get(business=self.business)
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
        
        Returns:
            Dict con datos del emisor:
            {
                'legal_name': str,
                'tax_id': str,
                'tax_id_display': str (formateado),
                'vat_condition': str,
                'vat_condition_display': str,
                'legal_address': str,
                'commercial_address': str,
                'city': str,
                'state_province': str,
                'postal_code': str,
                'country': str,
                'phone': str,
                'email': str,
                'website': str,
            }
        """
        profile = self.billing_profile
        return {
            'legal_name': profile.legal_name,
            'tax_id': profile.tax_id,
            'tax_id_display': f"{profile.get_tax_id_type_display()}: {profile.tax_id}" if profile.tax_id else '',
            'vat_condition': profile.vat_condition,
            'vat_condition_display': profile.get_vat_condition_display(),
            'legal_address': profile.legal_address,
            'commercial_address': profile.commercial_address or profile.legal_address,
            'city': profile.city,
            'state_province': profile.state_province,
            'postal_code': profile.postal_code,
            'country': profile.country,
            'phone': profile.phone,
            'email': profile.email,
            'website': profile.website,
        }
    
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
            'logo_horizontal': branding.logo_horizontal,
            'logo_square': branding.logo_square,
            'accent_color': branding.accent_color,
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
