export interface FAQItem {
    question: string;
    answer: string;
}

export interface FAQCategory {
    category: string;
    items: FAQItem[];
}

export const FAQ_DATA: FAQCategory[] = [
    {
        category: 'General',
        items: [
            {
                question: '¿Qué es Mi Rubro?',
                answer: 'Mi Rubro es una plataforma con herramientas digitales para comercios y locales. Actualmente ofrece soluciones para gestión comercial, menú QR online y QR para reseñas.',
            },
            {
                question: '¿Para qué tipo de negocios sirve?',
                answer: 'Mi Rubro está pensado para comercios y locales que buscan ordenar su gestión, mejorar su presencia digital y facilitar la interacción con sus clientes.',
            },
            {
                question: '¿Qué herramientas ofrece actualmente?',
                answer: 'Hoy Mi Rubro ofrece tres soluciones principales: Gestión Comercial, Menú QR Online y QR para reseñas.',
            },
        ],
    },
    {
        category: 'Productos',
        items: [
            {
                question: '¿Qué incluye Gestión Comercial?',
                answer: 'Gestión Comercial está orientado a ayudarte con la organización y administración diaria del negocio, según el alcance del servicio o plan contratado.',
            },
            {
                question: '¿Qué es Menú QR Online?',
                answer: 'Es una herramienta que te permite compartir tu menú o catálogo de forma digital mediante un código QR, para que tus clientes puedan verlo fácilmente desde el celular.',
            },
            {
                question: '¿Cómo funciona QR para reseñas?',
                answer: 'QR para reseñas facilita que tus clientes accedan rápidamente al espacio donde pueden dejar su opinión sobre tu local o negocio.',
            },
        ],
    },
    {
        category: 'Uso e implementación',
        items: [
            {
                question: '¿Necesito conocimientos técnicos para usar Mi Rubro?',
                answer: 'No. Mi Rubro está pensado para que su uso sea simple y accesible, incluso para personas que no tienen conocimientos técnicos avanzados.',
            },
            {
                question: '¿Puedo usarlo desde el celular?',
                answer: 'Sí, según la funcionalidad, podés acceder y gestionar información desde dispositivos móviles.',
            },
            {
                question: '¿Puedo actualizar la información de mi negocio o menú cuando quiera?',
                answer: 'Sí, la idea es que puedas mantener actualizada la información vinculada a tu negocio y a las herramientas que tengas activas.',
            },
            {
                question: '¿Cómo empiezo a usar Mi Rubro?',
                answer: 'Podés solicitar una demo o contactarte con el equipo para conocer qué solución se adapta mejor a tu negocio.',
            },
        ],
    },
    {
        category: 'Soporte y contacto',
        items: [
            {
                question: '¿Cómo solicito soporte?',
                answer: 'Podés escribir a mirubrodigital@gmail.com o ingresar a la sección de soporte para enviarnos tu consulta de forma ordenada.',
            },
            {
                question: '¿Cuánto tarda el soporte en responder?',
                answer: 'Las consultas se responden entre 24 y 48 hs hábiles desde su recepción.',
            },
            {
                question: '¿Los planes son iguales para todos los negocios?',
                answer: 'No necesariamente. Los planes y alcances pueden variar según la solución y las necesidades de cada negocio.',
            },
            {
                question: '¿Cómo solicito una demo?',
                answer: 'Podés hacerlo desde la web a través del botón de solicitud de demo o por los canales de contacto disponibles.',
            },
        ],
    },
];
