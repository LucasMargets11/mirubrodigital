export interface AboutCard {
    title: string;
    text: string;
}

/* ── Problema ── */

export const PROBLEM_CARDS: AboutCard[] = [
    {
        title: 'Menos desorden operativo',
        text: 'Ayudar a organizar tareas y procesos cotidianos con herramientas más claras y fáciles de usar.',
    },
    {
        title: 'Más presencia digital',
        text: 'Permitir que cada negocio muestre mejor su información, menú o catálogo de forma accesible y actualizable.',
    },
    {
        title: 'Mejor vínculo con clientes',
        text: 'Facilitar puntos de contacto más ágiles, simples y directos entre el local y sus clientes.',
    },
    {
        title: 'Digitalización con criterio',
        text: 'Incorporar herramientas útiles sin volver más compleja la operación.',
    },
];

/* ── Productos ── */

export const PRODUCT_CARDS: AboutCard[] = [
    {
        title: 'Gestión Comercial',
        text: 'Una solución pensada para acompañar la organización y administración diaria del negocio, según el alcance del servicio o plan contratado.',
    },
    {
        title: 'Menú QR Online',
        text: 'Una herramienta para compartir el menú o catálogo de forma digital mediante un código QR, mejorando el acceso desde el celular.',
    },
    {
        title: 'QR para reseñas',
        text: 'Una solución para facilitar que los clientes accedan rápidamente al canal donde pueden dejar su opinión sobre el local o negocio.',
    },
];

/* ── Cómo trabajamos ── */

export const PROCESS_PILLARS: AboutCard[] = [
    {
        title: 'Enfoque práctico',
        text: 'Diseñamos herramientas pensadas para ser útiles en la operación real del negocio.',
    },
    {
        title: 'Simplicidad',
        text: 'Buscamos que la experiencia sea clara, ordenada y fácil de incorporar.',
    },
    {
        title: 'Mejora continua',
        text: 'La plataforma evoluciona a partir de necesidades concretas y aprendizajes reales de uso.',
    },
    {
        title: 'Acompañamiento',
        text: 'Priorizamos una implementación cercana, con canales de contacto y soporte accesibles.',
    },
];

/* ── Por qué elegirnos ── */

export const WHY_CHOOSE = [
    'Herramientas enfocadas en necesidades concretas',
    'Experiencia simple y clara',
    'Soluciones digitales para comercios y locales',
    'Implementación realista',
    'Enfoque en utilidad, no en complejidad',
    'Evolución progresiva de la plataforma',
] as const;

/* ── Estudio VIZION ── */

export const VIZION_PILLARS: AboutCard[] = [
    {
        title: 'Visión de producto',
        text: 'Pensamos cada solución con foco en utilidad, evolución y adopción real.',
    },
    {
        title: 'Experiencia digital',
        text: 'Diseñamos interfaces y recorridos simples, claros y consistentes.',
    },
    {
        title: 'Desarrollo con criterio',
        text: 'Construimos herramientas preparadas para crecer de forma ordenada.',
    },
];
