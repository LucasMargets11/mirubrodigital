'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { INDUSTRIES } from './data';

export function IndustriesSection() {
    const [activeIndustry, setActiveIndustry] = useState(INDUSTRIES[0]);

    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="space-y-6">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">Soluciones</p>
                <h2 className="text-3xl font-semibold text-zinc-900">Hecho para negocios reales</h2>
                <div className="flex flex-wrap gap-3">
                    {INDUSTRIES.map((industry) => (
                        <button
                            key={industry.id}
                            type="button"
                            onClick={() => setActiveIndustry(industry)}
                            className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors ${activeIndustry.id === industry.id
                                    ? 'border-primary bg-primary text-white'
                                    : 'border-zinc-200 bg-white text-zinc-600 hover:border-primary/40'
                                }`}
                            aria-pressed={activeIndustry.id === industry.id}
                        >
                            {industry.label}
                        </button>
                    ))}
                </div>
                <div className="rounded-3xl border border-zinc-200 bg-white p-6 shadow-sm">
                    <p className="text-base text-zinc-600">{activeIndustry.highlight}</p>
                    <h3 className="mt-3 text-2xl font-semibold text-zinc-900">{activeIndustry.description}</h3>
                    <ul className="mt-6 space-y-3 text-sm text-zinc-600">
                        {activeIndustry.bullets.map((bullet) => (
                            <li key={bullet} className="flex items-start gap-3">
                                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                                {bullet}
                            </li>
                        ))}
                    </ul>
                    <div className="mt-6">
                        <Button asChild>
                            <Link href="/features">Ver funciones</Link>
                        </Button>
                    </div>
                </div>
            </div>
            </div>
        </section>
    );
}
