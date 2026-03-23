import {
    Presentation,
    CreditCard,
    Compass,
    Store,
    QrCode,
    Star,
    HelpCircle,
} from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { CONTACT_TOPICS } from '../_constants';

const ICONS = [Presentation, CreditCard, Compass, Store, QrCode, Star, HelpCircle] as const;

export function ContactTopics() {
    return (
        <section>
            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                ¿Sobre qué podés escribirnos?
            </h2>

            <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                {CONTACT_TOPICS.map((topic, i) => {
                    const Icon = ICONS[i]!;
                    return (
                        <li
                            key={topic}
                            className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
                        >
                            <span className="mt-0.5 flex-shrink-0 text-brand-600">
                                <Icon className="h-4 w-4" />
                            </span>
                            <span className="text-sm leading-relaxed text-slate-700">
                                {topic}
                            </span>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
