import {
    KeyRound,
    Settings,
    BarChart3,
    QrCode,
    Star,
    AlertTriangle,
    HelpCircle,
} from 'lucide-react';
import { SUPPORT_TOPICS } from '../_constants';

const ICONS = [
    KeyRound,
    Settings,
    BarChart3,
    QrCode,
    Star,
    AlertTriangle,
    HelpCircle,
] as const;

export function SupportTopics() {
    return (
        <section>
            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                ¿Con qué podemos ayudarte?
            </h2>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                {SUPPORT_TOPICS.map((topic, i) => {
                    const Icon = ICONS[i];
                    return (
                        <li
                            key={topic}
                            className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm"
                        >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                                <Icon className="h-4 w-4" />
                            </span>
                            {topic}
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
