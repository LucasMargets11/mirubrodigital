import Link from 'next/link';
import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SiteContainer } from '@/components/layout/site-container';
import { allPosts, featuredPost, categories } from '@/app/(marketing)/blog/_data';
import type { BlogPost } from '@/app/(marketing)/blog/_data';

// Helper to format date
const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('es-AR', {
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    });
};

// Helper: Get category label and color based on slug
const getCategoryDetails = (slug: string) => {
    const category = categories.find(c => c.slug === slug);
    const label = category ? category.label : slug;
    
    // Color mapping
    const colors: Record<string, string> = {
        gestion: 'bg-blue-50 text-blue-700 ring-blue-600/10',
        inventario: 'bg-amber-50 text-amber-700 ring-amber-600/10',
        ventas: 'bg-emerald-50 text-emerald-700 ring-emerald-600/10',
        caja: 'bg-slate-50 text-slate-700 ring-slate-600/10',
        marketing: 'bg-rose-50 text-rose-700 ring-rose-600/10',
        facturacion: 'bg-cyan-50 text-cyan-700 ring-cyan-600/10',
    };

    const colorClass = colors[slug] || 'bg-slate-50 text-slate-700 ring-slate-600/10';

    return { label, colorClass };
};

// Component: Large/Featured Card
function FeaturedPostCard({ post, priority = false }: { post: BlogPost; priority?: boolean }) {
    const { label: categoryLabel } = getCategoryDetails(post.category);

    return (
        <Link href={`/blog/${post.slug}`} className="group block h-full">
            <article className="flex flex-col h-full overflow-hidden rounded-2xl bg-white border border-slate-200 shadow-sm transition-all duration-300 hover:shadow-md hover:border-brand-300">
                <div className="relative aspect-[4/3] w-full overflow-hidden bg-slate-100">
                    <Image
                        src={post.coverImageUrl}
                        alt={post.title}
                        fill
                        priority={priority}
                        className="object-cover transition-transform duration-500 group-hover:scale-105"
                        sizes="(max-width: 768px) 100vw, 50vw"
                    />
                    <div className="absolute top-4 left-4">
                        <Badge variant="secondary" className="bg-white/90 backdrop-blur-sm text-brand-700 font-semibold shadow-sm hover:bg-white">
                            {categoryLabel}
                        </Badge>
                    </div>
                </div>
                <div className="flex flex-1 flex-col p-6">
                    <h3 className="text-xl font-bold text-slate-900 mb-3 leading-snug group-hover:text-brand-600 transition-colors">
                        {post.title}
                    </h3>
                    <p className="text-slate-600 text-sm leading-relaxed line-clamp-3 mb-6 flex-1">
                        {post.excerpt}
                    </p>
                    
                    <div className="flex items-center justify-between mt-auto">
                        <div className="flex items-center gap-3 text-xs font-medium text-slate-400">
                            <span className="uppercase tracking-wider text-brand-600 font-bold">{post.sourceLabel}</span>
                            <span className="h-1 w-1 rounded-full bg-slate-300" />
                            <time dateTime={post.date}>{formatDate(post.date)}</time>
                            <span className="h-1 w-1 rounded-full bg-slate-300" />
                            <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {post.readingTime}
                            </span>
                        </div>
                    </div>
                </div>
            </article>
        </Link>
    );
}

// Component: Editorial List Item (New sidebar style)
function EditorialPostListItem({ post }: { post: BlogPost }) {
    const { label: categoryLabel, colorClass } = getCategoryDetails(post.category);
    
    // Formato de fecha tipo: 1 SEP 2025
    const dateFormatted = new Date(post.date).toLocaleDateString('es-AR', {
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    }).toUpperCase().replace('.', '');

    return (
        <Link href={`/blog/${post.slug}`} className="group block py-1">
            <article className="flex flex-col gap-2">
                {/* Badge / Categoría */}
                <div className="flex items-center">
                    <span className={cn("px-2 py-0.5 rounded text-[10px] font-semibold tracking-wide uppercase transition-colors ring-1 ring-inset", colorClass)}>
                        {categoryLabel}
                    </span>
                </div>

                {/* Título */}
                <h4 className="text-base font-bold text-slate-900 leading-snug group-hover:text-brand-600 transition-colors line-clamp-2 font-display">
                    {post.title}
                </h4>

                {/* Metadatos */}
                <div className="flex items-center gap-2 text-[10px] sm:text-xs font-medium text-slate-400 uppercase tracking-wide">
                    <span>Artículo</span>
                    <span className="text-slate-300">•</span>
                    <time dateTime={post.date}>
                        {dateFormatted}
                    </time>
                    <span className="text-slate-300">•</span>
                    <span>{post.readingTime}</span>
                </div>
            </article>
        </Link>
    );
}

// Component: Wide/Bottom Card (Bottom row) - Vertical Layout but Wide
function WidePostCard({ post }: { post: BlogPost }) {
    const { label: categoryLabel } = getCategoryDetails(post.category);

    return (
        <Link href={`/blog/${post.slug}`} className="group block h-full">
            <article className="flex flex-col h-full overflow-hidden rounded-2xl bg-white border border-slate-200 shadow-sm transition-all duration-300 hover:shadow-md hover:border-brand-200">
                <div className="relative w-full aspect-[2.4/1] overflow-hidden bg-slate-100">
                    <Image
                        src={post.coverImageUrl}
                        alt={post.title}
                        fill
                        className="object-cover transition-transform duration-500 group-hover:scale-105"
                        sizes="(max-width: 640px) 100vw, 50vw"
                    />
                    <div className="absolute top-4 left-4">
                        <Badge variant="secondary" className="bg-white/90 backdrop-blur-sm text-slate-700 hover:bg-white text-[10px] h-5 px-2 font-medium border-slate-200 shadow-sm">
                            {categoryLabel}
                        </Badge>
                    </div>
                </div>
                <div className="flex-1 p-5 sm:p-6 flex flex-col">
                    <div className="flex items-center gap-2 text-xs text-slate-500 mb-2.5">
                        <time>{formatDate(post.date)}</time>
                        <span className="h-1 w-1 rounded-full bg-slate-300" />
                        <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {post.readingTime}
                        </span>
                    </div>
                    <h3 className="text-xl font-bold text-slate-900 mb-3 leading-snug group-hover:text-brand-600 transition-colors">
                        {post.title}
                    </h3>
                    <p className="text-slate-600 text-sm line-clamp-2 mb-4 leading-relaxed flex-1">
                        {post.excerpt}
                    </p>
                    <span className="text-xs font-semibold text-brand-600 flex items-center mt-auto uppercase tracking-wide group/link">
                        Leer artículo <ArrowRight className="w-3.5 h-3.5 ml-1.5 transition-transform group-hover/link:translate-x-1" />
                    </span>
                </div>
            </article>
        </Link>
    );
}

// Helper to get posts for home structure
function getHomePosts() {
    // 1. Featured posts: Use 'featuredPost' + 1st from 'allPosts' (excluding featured if duplicate)
    const featuredMain = featuredPost;
    const others = allPosts.filter(p => p.slug !== featuredMain.slug);
    
    // We need:
    // - 2 vertical featured (main + others[0])
    // - 3 editorial text items (others[1..3])
    // - 2 horizontal (others[4..5])
    
    const featuredSecondary = others[0];
    const compactPosts = others.slice(1, 4);
    const horizontalPosts = others.slice(4, 6); // Take 2
    
    return {
        featuredPosts: [featuredMain, featuredSecondary].filter(Boolean),
        compactPosts,
        horizontalPosts
    };
}

// Main Section Component
export function BlogResourcesSection() {
    const { featuredPosts, compactPosts, horizontalPosts } = getHomePosts();

    return (
        <section className="bg-white py-16 lg:py-24 border-t border-slate-100">
            <SiteContainer>
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 gap-4">
                    <div className="max-w-2xl">
                        <span className="text-brand-600 font-semibold tracking-wide uppercase text-sm mb-2 block">
                            Academia MiRubro
                        </span>
                        <h2 className="text-3xl font-display font-bold text-slate-900 tracking-tight sm:text-4xl">
                            Recursos y estrategias
                        </h2>
                        <p className="mt-3 text-lg text-slate-600 max-w-xl">
                            Guías prácticas y novedades para potenciar tu gestión.
                        </p>
                    </div>
                </div>

                {/* Editorial Layout */}
                <div className="flex flex-col gap-6 lg:gap-8">
                    
                    {/* Top Row: 3 Cols (Card | Card | TextStack) */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
                        {/* Col 1: Featured 1 */}
                        {featuredPosts[0] && (
                            <div className="h-full">
                                <FeaturedPostCard post={featuredPosts[0]} priority={true} />
                            </div>
                        )}
                        
                        {/* Col 2: Featured 2 */}
                        {featuredPosts[1] && (
                            <div className="h-full">
                                <FeaturedPostCard post={featuredPosts[1]} />
                            </div>
                        )}
                        
                        {/* Col 3: Text Stack / Editorial Column */}
                        <div className="flex flex-col h-full pl-0 lg:pl-2">
                            <div className="flex items-center justify-between mb-5 pb-2 border-b border-slate-200">
                                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-widest">
                                    Lo más nuevo
                                </h3>
                            </div>
                            
                            <div className="flex flex-col divide-y divide-slate-100">
                                {compactPosts.map((post) => (
                                    <div key={post.slug} className="py-5 first:pt-0 last:pb-0">
                                        <EditorialPostListItem post={post} />
                                    </div>
                                ))}
                            </div>

                            <div className="mt-6 pt-4 border-t border-slate-200 lg:hidden">
                                <Button asChild variant="link" className="p-0 h-auto text-brand-600">
                                    <Link href="/blog">Ver más artículos &rarr;</Link>
                                </Button>
                            </div>
                        </div>
                    </div>

                    {/* Bottom Row: 2 Wide Cards (50% each) */}
                    {horizontalPosts.length > 0 && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8">
                            {horizontalPosts.map((post) => (
                                <div key={post.slug} className="h-full">
                                    <WidePostCard post={post} />
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Final Centered CTA */}
                <div className="mt-12 lg:mt-16 flex justify-center">
                    <Button asChild size="lg" className="rounded-full px-9 py-6 text-base bg-brand-600 border-0 text-white font-semibold shadow-lg shadow-brand-600/30 relative overflow-hidden group">
                        <Link href="/blog">
                            <span className="relative z-10">Ver todos nuestros recursos</span>
                            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-brand-800 rounded-full scale-0 group-hover:scale-100 transition-transform duration-500 ease-out z-0" />
                        </Link>
                    </Button>
                </div>
            </SiteContainer>
        </section>
    );
}
