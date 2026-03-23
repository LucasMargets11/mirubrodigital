import { SUPPORT_WHATSAPP_NUMBER } from './_constants';

export interface SupportFormData {
    businessName: string;
    email: string;
    product: string;
    description: string;
    extra: string;
}

/**
 * Construye el mensaje de texto para enviar por WhatsApp con los datos del formulario.
 */
export function buildSupportMessage(data: SupportFormData): string {
    const extra = data.extra.trim() || 'No agregó información adicional';

    return [
        'Hola, necesito soporte de Mi Rubro.',
        '',
        `Nombre del comercio o local: ${data.businessName.trim()}`,
        `Email registrado: ${data.email.trim()}`,
        `Producto o módulo consultado: ${data.product}`,
        `Descripción del problema: ${data.description.trim()}`,
        `Capturas o información adicional: ${extra}`,
        '',
        'Gracias.',
    ].join('\n');
}

/**
 * Genera la URL de WhatsApp con el mensaje prellenado.
 * Usa https://wa.me/ que es el formato oficial de WhatsApp.
 */
export function buildWhatsAppUrl(message: string): string {
    const encoded = encodeURIComponent(message);
    return `https://wa.me/${SUPPORT_WHATSAPP_NUMBER}?text=${encoded}`;
}
