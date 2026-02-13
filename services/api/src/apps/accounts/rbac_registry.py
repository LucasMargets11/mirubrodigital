"""
RBAC Capability Registry - Shared module for all Mirubro services.

This module provides a centralized registry for all permissions/capabilities
across all services, with human-friendly descriptions grouped by module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class Capability:
    """Represents a permission/capability with metadata."""
    code: str
    title: str
    description: str
    module: str  # e.g., "Ventas", "Stock", "Finanzas", "Restaurante"
    service: str  # e.g., "gestion", "restaurante", "menu_qr"


class CapabilityRegistry:
    """Central registry for all capabilities across services."""
    
    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._by_service: Dict[str, Set[str]] = {}
        self._by_module: Dict[str, Set[str]] = {}
    
    def register(self, capability: Capability) -> None:
        """Register a new capability."""
        self._capabilities[capability.code] = capability
        
        if capability.service not in self._by_service:
            self._by_service[capability.service] = set()
        self._by_service[capability.service].add(capability.code)
        
        if capability.module not in self._by_module:
            self._by_module[capability.module] = set()
        self._by_module[capability.module].add(capability.code)
    
    def get(self, code: str) -> Capability | None:
        """Get capability by code."""
        return self._capabilities.get(code)
    
    def get_by_service(self, service: str) -> List[Capability]:
        """Get all capabilities for a service."""
        codes = self._by_service.get(service, set())
        return [self._capabilities[code] for code in codes]
    
    def get_by_module(self, module: str) -> List[Capability]:
        """Get all capabilities for a module."""
        codes = self._by_module.get(module, set())
        return [self._capabilities[code] for code in codes]
    
    def get_all(self) -> List[Capability]:
        """Get all registered capabilities."""
        return list(self._capabilities.values())
    
    def group_by_module(self, codes: Set[str]) -> Dict[str, List[Capability]]:
        """Group a set of capability codes by module."""
        result: Dict[str, List[Capability]] = {}
        for code in codes:
            cap = self._capabilities.get(code)
            if cap:
                if cap.module not in result:
                    result[cap.module] = []
                result[cap.module].append(cap)
        return result


# Global registry instance
_registry = CapabilityRegistry()


def get_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    return _registry


def register_capability(code: str, title: str, description: str, module: str, service: str) -> None:
    """Helper to register a capability."""
    capability = Capability(
        code=code,
        title=title,
        description=description,
        module=module,
        service=service
    )
    _registry.register(capability)


# ============================================================================
# GESTION SERVICE CAPABILITIES
# ============================================================================

def _register_gestion_capabilities():
    """Register all capabilities for Gestion Comercial service."""
    
    # Dashboard
    register_capability(
        'view_dashboard',
        'Ver Dashboard',
        'Acceso al panel principal con métricas y resúmenes del negocio',
        'Dashboard',
        'gestion'
    )
    
    # Products & Stock
    register_capability(
        'view_products',
        'Ver Productos',
        'Visualizar el catálogo de productos y sus detalles',
        'Stock',
        'gestion'
    )
    register_capability(
        'manage_products',
        'Gestionar Productos',
        'Crear, editar y eliminar productos del catálogo',
        'Stock',
        'gestion'
    )
    register_capability(
        'view_stock',
        'Ver Stock',
        'Consultar niveles de inventario y movimientos',
        'Stock',
        'gestion'
    )
    register_capability(
        'manage_stock',
        'Gestionar Stock',
        'Ajustar inventario, registrar entradas y salidas',
        'Stock',
        'gestion'
    )
    
    # Sales
    register_capability(
        'view_sales',
        'Ver Ventas',
        'Consultar ventas realizadas e historial',
        'Ventas',
        'gestion'
    )
    register_capability(
        'create_sales',
        'Crear Ventas',
        'Registrar nuevas operaciones de venta',
        'Ventas',
        'gestion'
    )
    register_capability(
        'cancel_sales',
        'Cancelar Ventas',
        'Anular ventas existentes (requiere aprobación)',
        'Ventas',
        'gestion'
    )
    
    # Invoices
    register_capability(
        'view_invoices',
        'Ver Facturas',
        'Consultar facturas emitidas',
        'Finanzas',
        'gestion'
    )
    register_capability(
        'issue_invoices',
        'Emitir Facturas',
        'Generar facturas y comprobantes fiscales',
        'Finanzas',
        'gestion'
    )
    register_capability(
        'void_invoices',
        'Anular Facturas',
        'Anular facturas emitidas (operación crítica)',
        'Finanzas',
        'gestion'
    )
    
    # Customers
    register_capability(
        'view_customers',
        'Ver Clientes',
        'Consultar base de datos de clientes',
        'Clientes',
        'gestion'
    )
    register_capability(
        'manage_customers',
        'Gestionar Clientes',
        'Crear, editar y administrar clientes',
        'Clientes',
        'gestion'
    )
    
    # Cash
    register_capability(
        'view_cash',
        'Ver Caja',
        'Consultar movimientos de caja y saldos',
        'Finanzas',
        'gestion'
    )
    register_capability(
        'manage_cash',
        'Gestionar Caja',
        'Abrir/cerrar cajas y registrar movimientos',
        'Finanzas',
        'gestion'
    )
    
    # Reports
    register_capability(
        'view_reports',
        'Ver Reportes',
        'Acceso a reportes generales del negocio',
        'Reportes',
        'gestion'
    )
    register_capability(
        'view_reports_sales',
        'Ver Reportes de Ventas',
        'Consultar análisis de ventas detallado',
        'Reportes',
        'gestion'
    )
    register_capability(
        'view_reports_cash',
        'Ver Reportes de Caja',
        'Consultar análisis de flujo de efectivo',
        'Reportes',
        'gestion'
    )
    register_capability(
        'view_reports_products',
        'Ver Reportes de Productos',
        'Consultar análisis de productos y stock',
        'Reportes',
        'gestion'
    )
    register_capability(
        'export_reports',
        'Exportar Reportes',
        'Descargar reportes en Excel/PDF',
        'Reportes',
        'gestion'
    )
    
    # Finance
    register_capability(
        'view_finance',
        'Ver Finanzas',
        'Consultar información financiera general',
        'Finanzas',
        'gestion'
    )
    register_capability(
        'manage_finance',
        'Gestionar Finanzas',
        'Administrar operaciones financieras avanzadas',
        'Finanzas',
        'gestion'
    )
    
    # Admin
    register_capability(
        'manage_users',
        'Gestionar Usuarios',
        'Administrar cuentas, roles y accesos (solo Owner)',
        'Configuración',
        'gestion'
    )
    register_capability(
        'manage_settings',
        'Gestionar Configuración',
        'Modificar configuración general del negocio',
        'Configuración',
        'gestion'
    )
    register_capability(
        'manage_commercial_settings',
        'Gestionar Config. Comercial',
        'Modificar configuración de ventas y operación',
        'Configuración',
        'gestion'
    )


# ============================================================================
# RESTAURANT SERVICE CAPABILITIES
# ============================================================================

def _register_restaurant_capabilities():
    """Register all capabilities for Restaurant service."""
    
    # Dashboard
    register_capability(
        'view_restaurant_dashboard',
        'Ver Dashboard Restaurante',
        'Panel principal con métricas del restaurante',
        'Dashboard',
        'restaurante'
    )
    
    # Orders
    register_capability(
        'view_orders',
        'Ver Pedidos',
        'Consultar pedidos en curso y completados',
        'Pedidos',
        'restaurante'
    )
    register_capability(
        'create_orders',
        'Crear Pedidos',
        'Tomar pedidos nuevos de clientes',
        'Pedidos',
        'restaurante'
    )
    register_capability(
        'edit_orders',
        'Editar Pedidos',
        'Modificar pedidos existentes',
        'Pedidos',
        'restaurante'
    )
    register_capability(
        'change_order_status',
        'Cambiar Estado de Pedidos',
        'Actualizar estado del pedido (preparando, listo, entregado)',
        'Pedidos',
        'restaurante'
    )
    register_capability(
        'close_orders',
        'Cerrar Pedidos',
        'Finalizar pedidos y cobrar',
        'Pedidos',
        'restaurante'
    )
    register_capability(
        'manage_order_table',
        'Asignar Mesas a Pedidos',
        'Vincular y cambiar mesas en pedidos',
        'Pedidos',
        'restaurante'
    )
    
    # Tables
    register_capability(
        'view_tables',
        'Ver Mesas',
        'Consultar estado de mesas del salón',
        'Salón',
        'restaurante'
    )
    register_capability(
        'manage_tables',
        'Gestionar Mesas',
        'Configurar y administrar mesas',
        'Salón',
        'restaurante'
    )
    
    # Menu
    register_capability(
        'view_menu',
        'Ver Menú',
        'Consultar carta de productos',
        'Menú',
        'restaurante'
    )
    register_capability(
        'manage_menu',
        'Gestionar Menú',
        'Editar productos, precios y disponibilidad',
        'Menú',
        'restaurante'
    )
    register_capability(
        'import_menu',
        'Importar Menú',
        'Cargar productos masivamente desde archivo',
        'Menú',
        'restaurante'
    )
    register_capability(
        'export_menu',
        'Exportar Menú',
        'Descargar carta en formato Excel/PDF',
        'Menú',
        'restaurante'
    )
    
    # Kitchen
    register_capability(
        'view_kitchen_board',
        'Ver Panel de Cocina',
        'Monitor de pedidos para preparación',
        'Cocina',
        'restaurante'
    )
    register_capability(
        'kitchen_update_status',
        'Actualizar Estado en Cocina',
        'Marcar platillos como preparados',
        'Cocina',
        'restaurante'
    )
    
    # Cash (inherited from gestion)
    register_capability(
        'view_cash',
        'Ver Caja',
        'Consultar movimientos de caja y saldos',
        'Finanzas',
        'restaurante'
    )
    register_capability(
        'manage_cash',
        'Gestionar Caja',
        'Abrir/cerrar cajas y registrar movimientos',
        'Finanzas',
        'restaurante'
    )
    
    # Reports
    register_capability(
        'view_restaurant_reports',
        'Ver Reportes',
        'Consultar análisis de operación del restaurante',
        'Reportes',
        'restaurante'
    )
    
    # Settings
    register_capability(
        'manage_users',
        'Gestionar Usuarios',
        'Administrar cuentas, roles y accesos (solo Owner)',
        'Configuración',
        'restaurante'
    )
    register_capability(
        'manage_settings',
        'Gestionar Configuración',
        'Modificar configuración general del restaurante',
        'Configuración',
        'restaurante'
    )
    register_capability(
        'manage_whatsapp_bot',
        'Gestionar Bot WhatsApp',
        'Configurar integración con WhatsApp',
        'Configuración',
        'restaurante'
    )
    register_capability(
        'manage_menu_branding',
        'Gestionar Branding de Menú',
        'Personalizar apariencia del menú online',
        'Configuración',
        'restaurante'
    )
    register_capability(
        'view_menu_admin',
        'Administrar Menú Online',
        'Panel de control del menú público',
        'Menú',
        'restaurante'
    )
    register_capability(
        'view_public_menu',
        'Ver Menú Público',
        'Acceso al menú QR visible a clientes',
        'Menú',
        'restaurante'
    )


# ============================================================================
# MENU QR SERVICE CAPABILITIES
# ============================================================================

def _register_menu_qr_capabilities():
    """Register all capabilities for Menu QR service."""
    
    register_capability(
        'view_menu',
        'Ver Menú',
        'Consultar carta de productos',
        'Menú',
        'menu_qr'
    )
    register_capability(
        'manage_menu',
        'Gestionar Menú',
        'Editar productos, precios y disponibilidad',
        'Menú',
        'menu_qr'
    )
    register_capability(
        'manage_menu_branding',
        'Gestionar Branding',
        'Personalizar logo, colores y estilo del menú',
        'Configuración',
        'menu_qr'
    )
    register_capability(
        'view_menu_admin',
        'Panel de Administración',
        'Panel de control del menú online',
        'Menú',
        'menu_qr'
    )
    register_capability(
        'view_public_menu',
        'Ver Menú Público',
        'Acceso al menú QR visible a clientes',
        'Menú',
        'menu_qr'
    )
    register_capability(
        'manage_settings',
        'Gestionar Configuración',
        'Modificar configuración general',
        'Configuración',
        'menu_qr'
    )
    register_capability(
        'manage_users',
        'Gestionar Usuarios',
        'Administrar cuentas y accesos (solo Owner)',
        'Configuración',
        'menu_qr'
    )


# Initialize registry on module load
_register_gestion_capabilities()
_register_restaurant_capabilities()
_register_menu_qr_capabilities()
