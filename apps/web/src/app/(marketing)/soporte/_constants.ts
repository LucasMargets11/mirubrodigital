/**
 * Constantes configurables de la página de soporte.
 *
 * TODO: confirmar formato internacional definitivo de WhatsApp para producción
 * si se requiere prefijo país (ej: 5493764705901 para Argentina móvil).
 * Por ahora se usa el número tal cual fue informado.
 */

export const SUPPORT_EMAIL = 'mirubrodigital@gmail.com';

/**
 * Número de WhatsApp para soporte.
 * Se utiliza en la URL de wa.me sin el "+" inicial.
 * Para Argentina móvil el formato internacional completo sería 5493764705901.
 */
export const SUPPORT_WHATSAPP_NUMBER = '5493764705901';

/** Número visible para mostrar en la UI */
export const SUPPORT_WHATSAPP_DISPLAY = '376 470-5901';

export const SUPPORT_TOPICS = [
    'Acceso a tu cuenta',
    'Configuración inicial',
    'Gestión Comercial',
    'Menú QR Online',
    'QR para reseñas',
    'Errores o problemas técnicos',
    'Consultas generales sobre el servicio',
] as const;

export const PRODUCT_OPTIONS = [
    { value: '', label: 'Seleccioná un producto o módulo' },
    { value: 'Gestión Comercial', label: 'Gestión Comercial' },
    { value: 'Menú QR Online', label: 'Menú QR Online' },
    { value: 'QR para reseñas', label: 'QR para reseñas' },
    { value: 'Otro', label: 'Otro' },
] as const;

export const USEFUL_LINKS = [
    { href: '/preguntas-frecuentes', label: 'Preguntas frecuentes' },
    { href: '/contacto', label: 'Contacto' },
    { href: '/privacidad', label: 'Privacidad' },
    { href: '/terminos', label: 'Términos y condiciones' },
] as const;
