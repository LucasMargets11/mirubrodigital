/**
 * Blog mock data — centralizado para fácil reemplazo por CMS/backend.
 *
 * Para migrar a un CMS, reemplaza la exportación de estas constantes por
 * una función async que consulte la API y ajusta los componentes que las
 * consumen para await/suspense según lo que necesites.
 */

export interface BlogPost {
    /** Identificador único usado en la URL /blog/:slug */
    slug: string;
    title: string;
    /** Resumen breve para cards y hero (1–2 oraciones). */
    excerpt: string;
    /** URL de la imagen de portada. */
    coverImageUrl: string;
    /** Tiempo estimado de lectura, ej. "4 min". */
    readingTime: string;
    /** Fecha de publicación en formato ISO (YYYY-MM-DD). */
    date: string;
    /** Etiqueta de origen/brand, ej. "MIRUBRO". */
    sourceLabel: string;
    /** Slug de la categoría, ej. "inventario". */
    category: string;
}

export interface BlogCategory {
    slug: string;
    label: string;
}

/** Post destacado que aparece en el hero superior. */
export const featuredPost: BlogPost = {
    slug: 'como-digitalizar-tu-negocio-sin-complicaciones',
    title: 'Cómo digitalizar tu negocio sin complicaciones',
    excerpt:
        'Descubre los pasos clave para llevar tu operación al siguiente nivel con tecnología que se adapta a cada etapa de tu negocio, sin necesidad de ser experto en sistemas.',
    coverImageUrl: 'https://images.unsplash.com/photo-1556761175-4b46a572b786?w=900&auto=format&fit=crop&q=70',
    readingTime: '5 min',
    date: '2026-02-20',
    sourceLabel: 'MIRUBRO',
    category: 'gestion',
};

/** Lista de posts recientes para el grid. */
export const recentPosts: BlogPost[] = [
    {
        slug: 'gestion-de-inventario-eficiente-para-pymes',
        title: 'Gestión de inventario eficiente para PYMEs',
        excerpt:
            'Aprende a controlar tu stock en tiempo real y evita quiebres de inventario con procesos simples que escalan con tu equipo.',
        coverImageUrl: 'https://images.unsplash.com/photo-1553413077-190dd305871c?w=600&auto=format&fit=crop&q=70',
        readingTime: '4 min',
        date: '2026-02-14',
        sourceLabel: 'MIRUBRO',
        category: 'inventario',
    },
    {
        slug: 'menu-qr-como-aumentar-ventas-restaurante',
        title: 'Menú QR: cómo aumentar ventas en tu restaurante',
        excerpt:
            'Un menú digital bien diseñado no solo mejora la experiencia del comensal, también acelera el servicio y reduce errores en las órdenes.',
        coverImageUrl: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&auto=format&fit=crop&q=70',
        readingTime: '3 min',
        date: '2026-02-07',
        sourceLabel: 'MIRUBRO',
        category: 'ventas',
    },
    {
        slug: 'cierre-de-caja-sin-errores-guia-practica',
        title: 'Cierre de caja sin errores: guía práctica',
        excerpt:
            'El cierre de caja es uno de los procesos más críticos del día. Te contamos las mejores prácticas para que sea rápido, exacto y auditable.',
        coverImageUrl: 'https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=600&auto=format&fit=crop&q=70',
        readingTime: '6 min',
        date: '2026-01-28',
        sourceLabel: 'MIRUBRO',
        category: 'caja',
    },
    {
        slug: 'reportes-de-venta-que-datos-importan',
        title: 'Reportes de ventas: ¿qué datos importan realmente?',
        excerpt:
            'No todos los números cuentan la misma historia. Descubre los KPIs de ventas que deberías revisar cada semana para tomar mejores decisiones.',
        coverImageUrl: 'https://images.unsplash.com/photo-1543286386-713bdd548da4?w=600&auto=format&fit=crop&q=70',
        readingTime: '5 min',
        date: '2026-01-15',
        sourceLabel: 'MIRUBRO',
        category: 'ventas',
    },
    {
        slug: 'fidelizacion-de-clientes-estrategias',
        title: 'Fidelización de clientes: estrategias que funcionan',
        excerpt:
            'Retener a un cliente cuesta hasta 5 veces menos que conseguir uno nuevo. Aquí te mostramos cómo lograrlo con herramientas simples.',
        coverImageUrl: 'https://images.unsplash.com/photo-1521791136064-7986c2920216?w=600&auto=format&fit=crop&q=70',
        readingTime: '4 min',
        date: '2026-01-08',
        sourceLabel: 'MIRUBRO',
        category: 'marketing',
    },
    {
        slug: 'facturacion-electronica-primeros-pasos',
        title: 'Facturación electrónica: primeros pasos',
        excerpt:
            'La transición a la factura electrónica puede parecer compleja, pero con el proceso correcto tu negocio puede estar listo en menos de una semana.',
        coverImageUrl: 'https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=600&auto=format&fit=crop&q=70',
        readingTime: '7 min',
        date: '2025-12-20',
        sourceLabel: 'MIRUBRO',
        category: 'facturacion',
    },
];

/** Todas las categorías disponibles para filtrado. */
export const categories: BlogCategory[] = [
    { slug: 'gestion',     label: 'Gestión' },
    { slug: 'inventario',  label: 'Inventario' },
    { slug: 'ventas',      label: 'Ventas' },
    { slug: 'caja',        label: 'Caja' },
    { slug: 'facturacion', label: 'Facturación' },
    { slug: 'marketing',   label: 'Marketing' },
];

/** Todos los posts (featured + recientes) — útil para búsquedas por slug. */
export const allPosts: BlogPost[] = [featuredPost, ...recentPosts];

/** Recupera un post por slug, o undefined si no existe. */
export function getPostBySlug(slug: string): BlogPost | undefined {
    return allPosts.find((p) => p.slug === slug);
}

/**
 * Devuelve hasta `limit` posts relacionados al dado.
 * Criterio: misma categoría, excluyendo el actual.
 * Fallback: últimos posts excluyendo el actual.
 */
export function getRelatedPosts(current: BlogPost, limit = 3): BlogPost[] {
    const others = allPosts.filter((p) => p.slug !== current.slug);
    const sameCat = others.filter((p) => p.category === current.category);
    const pool = sameCat.length >= limit ? sameCat : [...sameCat, ...others.filter((p) => p.category !== current.category)];
    return pool.slice(0, limit);
}

/** Párrafos mock para el body de un artículo (placeholder hasta conectar CMS). */
export const mockBodyParagraphs: string[] = [
    'La transformación digital de un negocio no ocurre de la noche a la mañana, pero tampoco tiene que ser un proceso interminable. Con la estrategia correcta y las herramientas adecuadas, es posible dar pasos concretos desde el primer día.',
    'El primer paso siempre es entender qué procesos consumen más tiempo y cuáles generan más errores. Inventario desactualizado, cierres de caja manuales y reportes en hojas de cálculo son señales claras de que hay oportunidad de mejora.',
    'Una vez identificadas las fricciones, el siguiente paso es elegir una plataforma que centralice la operación. Lo ideal es que se adapte a tu ritmo: puedes empezar con una sola función y expandir a medida que el equipo se familiariza.',
    'La capacitación es clave. Una herramienta poderosa que nadie usa correctamente no resuelve nada. Dedicar tiempo a la formación inicial —aunque sean 2 o 3 horas— marca una diferencia enorme en la adopción.',
    'Finalmente, mide los resultados. ¿Cuánto tiempo ahorras en el cierre diario? ¿Cuántos errores de stock se redujeron? Los datos son el mejor argumento para seguir invirtiendo en tecnología.',
];
