import type { ProductDef } from './types';

export const ALL_PRODUCTS: readonly ProductDef[] = [
  {
    code: 'gestion',
    vertical: 'commercial',
    name: 'Gestión Comercial',
    description: 'Ventas, stock, clientes, caja y facturación para comercios.',
    is_active: true,
    order: 1,
  },
  {
    code: 'menu_qr',
    vertical: 'menu_qr',
    name: 'Menú QR',
    description: 'Carta digital con código QR para que tus clientes vean tu menú.',
    is_active: true,
    order: 2,
  },
  {
    code: 'qr_reviews',
    vertical: 'qr_reviews',
    name: 'QR de Reseñas',
    description: 'Sistema de feedback con filtro inteligente y redirección a Google.',
    is_active: true,
    order: 3,
  },
  {
    code: 'appointments',
    vertical: 'appointments',
    name: 'Turnos',
    description: 'Gestioná tu agenda y recibí reservas online.',
    is_active: false,
    order: 4,
  },
  {
    // PROD-02B: servicio independiente de Turnos. Sin venta pública: solo alta
    // interna (todavía no habilitada) hasta aprobar precios y cantidades.
    code: 'reception',
    vertical: 'reception',
    name: 'Recepcionista IA',
    description: 'Atención por WhatsApp con IA, leads y derivación a tu equipo.',
    is_active: false,
    order: 5,
  },
];
