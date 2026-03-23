import { Mail, MessageSquare } from 'lucide-react';
import {
    SUPPORT_EMAIL,
    SUPPORT_WHATSAPP_DISPLAY,
} from '../_constants';

export function SupportChannels() {
    return (
        <section>
            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                Canales de atención
            </h2>

            <div className="mt-6 space-y-4">
                {/* Email */}
                <div className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                        <Mail className="h-5 w-5" />
                    </span>
                    <div>
                        <p className="text-sm font-medium text-slate-900">Correo electrónico</p>
                        <a
                            href={`mailto:${SUPPORT_EMAIL}`}
                            className="text-sm text-brand-600 underline underline-offset-2 hover:text-brand-500"
                        >
                            {SUPPORT_EMAIL}
                        </a>
                    </div>
                </div>

                {/* WhatsApp */}
                <div className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-green-50 text-green-600">
                        <MessageSquare className="h-5 w-5" />
                    </span>
                    <div>
                        <p className="text-sm font-medium text-slate-900">WhatsApp</p>
                        <p className="text-sm text-slate-600">{SUPPORT_WHATSAPP_DISPLAY}</p>
                    </div>
                </div>
            </div>

            <p className="mt-4 text-sm leading-relaxed text-slate-500">
                Actualmente también podés enviarnos tu consulta por WhatsApp de forma
                provisional a través del formulario de esta página.
            </p>
        </section>
    );
}
