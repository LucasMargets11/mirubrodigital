/**
 * Constantes configurables de la página de contacto.
 *
 * TODO: confirmar formato internacional definitivo del número de WhatsApp
 * para producción si se requiere estandarizar (ej: 5493764705901).
 */

export const CONTACT_EMAIL = 'mirubrodigital@gmail.com';

/** Número de WhatsApp para contacto general.
 *  Se utiliza en la URL de wa.me sin el "+" inicial. */
export const CONTACT_WHATSAPP_NUMBER = '5493764705901';

/** Número visible para mostrar en la UI */
export const CONTACT_WHATSAPP_DISPLAY = '376 470-5901';

export const INQUIRY_OPTIONS = [
    { value: '', label: 'Seleccioná el tipo de consulta' },
    { value: 'Quiero solicitar una demo', label: 'Quiero solicitar una demo' },
    { value: 'Quiero conocer los planes', label: 'Quiero conocer los planes' },
    {
        value: 'Quiero más información sobre Gestión Comercial',
        label: 'Quiero más información sobre Gestión Comercial',
    },
    {
        value: 'Quiero más información sobre Menú QR Online',
        label: 'Quiero más información sobre Menú QR Online',
    },
    {
        value: 'Quiero más información sobre QR para reseñas',
        label: 'Quiero más información sobre QR para reseñas',
    },
    {
        value: 'Quiero hacer una consulta general',
        label: 'Quiero hacer una consulta general',
    },
    { value: 'Otro', label: 'Otro' },
] as const;

export const PREFERRED_CHANNEL_OPTIONS = [
    { value: 'Email', label: 'Email' },
    { value: 'WhatsApp', label: 'WhatsApp' },
] as const;

export const CONTACT_TOPICS = [
    'Solicitar una demo',
    'Consultar por planes',
    'Conocer qué solución se adapta mejor a tu negocio',
    'Obtener más información sobre Gestión Comercial',
    'Obtener más información sobre Menú QR Online',
    'Obtener más información sobre QR para reseñas',
    'Realizar consultas generales sobre Mi Rubro',
] as const;
