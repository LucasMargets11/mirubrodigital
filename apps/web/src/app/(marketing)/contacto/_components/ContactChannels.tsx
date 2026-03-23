import { Mail, MessageSquare } from 'lucide-react';
import {
    CONTACT_EMAIL,
    CONTACT_WHATSAPP_NUMBER,
    CONTACT_WHATSAPP_DISPLAY,
} from '../_constants';

export function ContactChannels() {
    return (
        <section>
            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                Canales de contacto
            </h2>

            <div className="mt-6 space-y-4">
                {/* Email */}
                <div className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                        <Mail className="h-5 w-5" />
                    </span>
                    <div>
                        <p className="text-sm font-medium text-slate-900">
                            Correo electrónico
                        </p>
                        <a
                            href={`mailto:${CONTACT_EMAIL}`}
                            className="text-sm text-brand-600 underline underline-offset-2 hover:text-brand-500"
                        >
                            {CONTACT_EMAIL}
                        </a>
                    </div>
                </div>

                {/* WhatsApp */}
                <div className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-green-50 text-green-600">
                        <MessageSquare className="h-5 w-5" />
                    </span>
                    <div>
                        <p className="text-sm font-medium text-slate-900">
                            WhatsApp
                        </p>
                        <a
                            href={`https://wa.me/${CONTACT_WHATSAPP_NUMBER}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-green-600 underline underline-offset-2 hover:text-green-500"
                        >
                            {CONTACT_WHATSAPP_DISPLAY}
                        </a>
                    </div>
                </div>
            </div>

            <p className="mt-4 text-sm leading-relaxed text-slate-500">
                Podés escribirnos por email o enviarnos tu consulta por
                WhatsApp. Si preferís, también podés completar el formulario de
                esta página para contactarnos de forma más ordenada.
            </p>
        </section>
    );
}
