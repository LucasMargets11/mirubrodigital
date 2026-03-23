import { CONTACT_EMAIL, CONTACT_WHATSAPP_NUMBER } from './_constants';

export interface ContactFormData {
    fullName: string;
    businessName: string;
    email: string;
    inquiryType: string;
    message: string;
    preferredChannel: string;
    phone: string;
}

/**
 * Construye el mensaje de texto para enviar por WhatsApp.
 */
export function buildContactWhatsAppMessage(data: ContactFormData): string {
    return [
        'Hola, quiero contactarme con Mi Rubro.',
        '',
        `Nombre y apellido: ${data.fullName.trim()}`,
        `Comercio o local: ${data.businessName.trim() || 'No indicado'}`,
        `Email: ${data.email.trim()}`,
        `Tipo de consulta: ${data.inquiryType}`,
        `Canal preferido de respuesta: ${data.preferredChannel}`,
        `Teléfono / WhatsApp de contacto: ${data.phone.trim() || 'No indicado'}`,
        `Mensaje: ${data.message.trim()}`,
        '',
        'Gracias.',
    ].join('\n');
}

/**
 * Genera la URL de WhatsApp con el mensaje prellenado.
 */
export function getContactWhatsAppUrl(message: string): string {
    return `https://wa.me/${CONTACT_WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}

/**
 * Genera un enlace mailto con asunto y cuerpo precompletado.
 */
export function buildContactMailtoLink(data: ContactFormData): string {
    const subject = encodeURIComponent('Consulta desde la web - Mi Rubro');
    const body = encodeURIComponent(
        [
            'Hola, quiero contactarme con Mi Rubro.',
            '',
            `Nombre y apellido: ${data.fullName.trim()}`,
            `Comercio o local: ${data.businessName.trim() || 'No indicado'}`,
            `Email: ${data.email.trim()}`,
            `Tipo de consulta: ${data.inquiryType}`,
            `Canal preferido de respuesta: ${data.preferredChannel}`,
            `Teléfono / WhatsApp de contacto: ${data.phone.trim() || 'No indicado'}`,
            `Mensaje: ${data.message.trim()}`,
            '',
            'Gracias.',
        ].join('\n'),
    );

    return `mailto:${CONTACT_EMAIL}?subject=${subject}&body=${body}`;
}
