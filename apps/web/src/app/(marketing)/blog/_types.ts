/** Tipos de bloque de contenido rico para posts nuevos. */
export type ContentBlock =
    | { type: 'h2'; text: string }
    | { type: 'h3'; text: string }
    | { type: 'p'; text: string }
    | { type: 'ul'; items: string[] }
    | { type: 'check'; items: string[] }
    | { type: 'cta'; text: string; href: string; buttonLabel: string }
    | { type: 'faq'; items: Array<{ q: string; a: string }> };

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
    /** SEO: título personalizado (si difiere del title). */
    metaTitle?: string;
    /** SEO: descripción personalizada para meta description. */
    metaDescription?: string;
    /** Contenido rico estructurado (posts nuevos). Si está vacío usa mockBodyParagraphs. */
    bodyContent?: ContentBlock[];
}

export interface BlogCategory {
    slug: string;
    label: string;
}
