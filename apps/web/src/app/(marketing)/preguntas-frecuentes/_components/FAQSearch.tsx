'use client';

import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import type { FAQCategory } from '../_data';
import { FAQCategorySection } from './FAQCategorySection';

interface Props {
    data: FAQCategory[];
}

export function FAQSearch({ data }: Props) {
    const [query, setQuery] = useState('');

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return data;

        return data
            .map((cat) => ({
                ...cat,
                items: cat.items.filter(
                    (item) =>
                        item.question.toLowerCase().includes(q) ||
                        item.answer.toLowerCase().includes(q),
                ),
            }))
            .filter((cat) => cat.items.length > 0);
    }, [data, query]);

    return (
        <>
            {/* Buscador */}
            <div className="relative mx-auto max-w-lg">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Buscá en las preguntas frecuentes..."
                    aria-label="Buscar preguntas frecuentes"
                    className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1"
                />
            </div>

            {/* Resultados */}
            {filtered.length > 0 ? (
                <div className="mt-10 space-y-10 sm:mt-12">
                    {filtered.map((cat) => (
                        <FAQCategorySection key={cat.category} category={cat} />
                    ))}
                </div>
            ) : (
                <p className="mt-12 text-center text-sm text-slate-500">
                    No encontramos resultados para tu búsqueda.
                </p>
            )}
        </>
    );
}
