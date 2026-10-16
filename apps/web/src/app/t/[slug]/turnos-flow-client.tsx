'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import type {
    AvailabilityResult,
    PublicAppointmentBooking,
    PublicAppointmentBusiness,
    PublicAppointmentProfessional,
    PublicAppointmentService,
} from '@/features/appointments/types';
import { syncBookingQuery, type PaymentReturnHint } from '@/features/appointments/public-booking';
import { DatePicker, formatLongDate } from '@/components/ui/date-picker';
import { resolveBusinessTimeZone, todayInTimeZone } from '@/lib/business-time';
import { BookingStatus } from './booking-status';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// `status`: "Estado de tu reserva" (confirmada, hold con seña, retorno de
// Mercado Pago...). Siempre resuelto contra el backend por `public_token`.
type Step = 'service' | 'professional' | 'datetime' | 'review' | 'status';

// Resolución de profesionales del servicio elegido (Slice 7B.1). El backend
// es la fuente de verdad: `200 + []` = servicio SIN profesionales; `200 +
// [...]` = profesional obligatorio. Cualquier otro resultado (429, 5xx, red,
// body inválido) es `error`: nunca se asume "sin profesionales".
type ProfessionalsState = 'idle' | 'loading' | 'ready' | 'error';

interface Props {
    slug: string;
    data: PublicAppointmentBusiness;
    /** `?booking=<public_token>`: restaura directamente el estado de la reserva. */
    initialBookingToken?: string | null;
    /** `?payment=`: pista visual de la back URL de Mercado Pago, nunca fuente de verdad. */
    paymentHint?: PaymentReturnHint | null;
}

function formatPrice(price: string): string {
    const value = Number(price);
    if (Number.isNaN(value)) return price;
    return `$ ${value.toLocaleString('es-AR')}`;
}

function formatDuration(minutes: number): string {
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

function formatDateDisplay(isoDate: string): string {
    const [year, month, day] = isoDate.split('-');
    return `${day}/${month}/${year}`;
}

export function TurnosFlowClient({ slug, data, initialBookingToken = null, paymentHint = null }: Props) {
    const [step, setStep] = useState<Step>(initialBookingToken ? 'status' : 'service');

    const [selectedService, setSelectedService] = useState<PublicAppointmentService | null>(null);
    const [professionals, setProfessionals] = useState<PublicAppointmentProfessional[]>([]);
    const [selectedProfessional, setSelectedProfessional] = useState<PublicAppointmentProfessional | null>(null);
    const [professionalsState, setProfessionalsState] = useState<ProfessionalsState>('idle');
    // Descarta respuestas de un servicio anterior si el usuario cambió de servicio.
    const professionalsRequestRef = useRef(0);

    const [selectedDate, setSelectedDate] = useState('');
    // "Hoy" (mínimo elegible) en la zona del Business, la misma con la que el
    // backend interpreta `?date=` en availability; nunca la del navegador.
    const businessToday = todayInTimeZone(resolveBusinessTimeZone(data.business.timezone));
    const [slots, setSlots] = useState<AvailabilityResult['slots']>([]);
    const [availabilityLoading, setAvailabilityLoading] = useState(false);
    const [availabilityError, setAvailabilityError] = useState('');
    const [selectedSlot, setSelectedSlot] = useState<AvailabilityResult['slots'][number] | null>(null);

    const [customerName, setCustomerName] = useState('');
    const [customerPhone, setCustomerPhone] = useState('');
    const [customerEmail, setCustomerEmail] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [booking, setBooking] = useState<PublicAppointmentBooking | null>(null);
    const [bookingToken, setBookingToken] = useState<string | null>(initialBookingToken);
    const [returnHint, setReturnHint] = useState<PaymentReturnHint | null>(paymentHint);

    // La pista `payment=` solo sirve para el primer render: se limpia de la URL
    // (queda `?booking=`), así un refresh no la vuelve a leer.
    useEffect(() => {
        if (initialBookingToken) syncBookingQuery(initialBookingToken);
    }, [initialBookingToken]);

    const servicesByCategory = useMemo(() => {
        const groups = new Map<string, { name: string; services: PublicAppointmentService[] }>();
        for (const service of data.services) {
            const key = service.category?.id ?? '__none__';
            const name = service.category?.name ?? 'Servicios';
            if (!groups.has(key)) groups.set(key, { name, services: [] });
            groups.get(key)!.services.push(service);
        }
        return Array.from(groups.values());
    }, [data.services]);

    async function loadProfessionals(service: PublicAppointmentService) {
        const requestId = ++professionalsRequestRef.current;
        setProfessionals([]);
        setSelectedProfessional(null);
        setProfessionalsState('loading');

        let list: PublicAppointmentProfessional[] | null = null;
        try {
            const res = await fetch(
                `${API_URL}/api/v1/appointments/public/${slug}/professionals/?service=${service.id}`,
            );
            if (res.ok) {
                const body: unknown = await res.json();
                if (Array.isArray(body)) list = body as PublicAppointmentProfessional[];
            }
        } catch {
            list = null;
        }
        if (requestId !== professionalsRequestRef.current) return;

        if (list === null) {
            setProfessionalsState('error');
            return;
        }
        setProfessionals(list);
        setProfessionalsState('ready');
        setStep(list.length > 0 ? 'professional' : 'datetime');
    }

    function handleSelectService(service: PublicAppointmentService) {
        // Cambiar de servicio invalida el profesional elegido: se vuelve a
        // resolver contra el backend para el servicio nuevo.
        setSelectedService(service);
        setSelectedDate('');
        setSlots([]);
        setSelectedSlot(null);
        setStep('professional');
        void loadProfessionals(service);
    }

    // Profesionales resueltos y, si el servicio los tiene, uno elegido.
    const professionalResolved =
        professionalsState === 'ready' && (professionals.length === 0 || selectedProfessional !== null);

    function handleSelectProfessional(professional: PublicAppointmentProfessional) {
        setSelectedProfessional(professional);
        setStep('datetime');
    }

    async function handleSelectDate(date: string) {
        setSelectedDate(date);
        setSelectedSlot(null);
        setSlots([]);
        setAvailabilityError('');
        if (!selectedService || !date || !professionalResolved) return;

        setAvailabilityLoading(true);
        try {
            const params = new URLSearchParams({ service: selectedService.id, date });
            if (selectedProfessional) params.set('professional', selectedProfessional.id);
            const res = await fetch(
                `${API_URL}/api/v1/appointments/public/${slug}/availability/?${params.toString()}`,
            );
            if (!res.ok) {
                setAvailabilityError('No pudimos consultar la disponibilidad. Probá con otra fecha.');
                return;
            }
            const result = (await res.json()) as AvailabilityResult;
            setSlots(result.slots);
        } catch {
            setAvailabilityError('Error de conexión. Intentá de nuevo.');
        } finally {
            setAvailabilityLoading(false);
        }
    }

    function handleSelectSlot(slot: AvailabilityResult['slots'][number]) {
        setSelectedSlot(slot);
        setStep('review');
    }

    function goBackTo(target: Step) {
        setStep(target);
    }

    function resetFlow() {
        professionalsRequestRef.current += 1;
        setStep('service');
        setSelectedService(null);
        setProfessionals([]);
        setProfessionalsState('idle');
        setSelectedProfessional(null);
        setSelectedDate('');
        setSlots([]);
        setSelectedSlot(null);
        setCustomerName('');
        setCustomerPhone('');
        setCustomerEmail('');
        setSubmitError('');
        setBooking(null);
        setBookingToken(null);
        setReturnHint(null);
        syncBookingQuery(null);
    }

    async function handleSubmitBooking() {
        // Nunca reservar sin haber resuelto los profesionales del servicio
        // (p.ej. `professional=null` tras un error de red).
        if (!selectedService || !selectedSlot || !professionalResolved) return;
        setSubmitting(true);
        setSubmitError('');
        try {
            const res = await fetch(`${API_URL}/api/v1/appointments/public/${slug}/bookings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    service: selectedService.id,
                    professional: selectedProfessional?.id ?? null,
                    start: selectedSlot.start,
                    customer_name: customerName,
                    customer_phone: customerPhone,
                    customer_email: customerEmail || undefined,
                }),
            });
            const data = await res.json().catch(() => null);
            if (!res.ok || !data) {
                const firstError =
                    data && typeof data === 'object'
                        ? (Object.values(data)[0] as string[] | undefined)?.[0]
                        : undefined;
                setSubmitError(firstError ?? 'No pudimos completar la reserva. Probá de nuevo.');
                return;
            }
            const created = data as PublicAppointmentBooking;
            setBooking(created);
            setBookingToken(created.public_token);
            // Refresh / volver atrás desde Mercado Pago restauran esta reserva.
            syncBookingQuery(created.public_token);
            setStep('status');
        } catch {
            setSubmitError('Error de conexión. Intentá de nuevo.');
        } finally {
            setSubmitting(false);
        }
    }

    const displayName = data.business.name;

    /* ── Step: Servicio ─────────────────────────────────────────── */
    if (step === 'service') {
        return (
            <Shell businessName={displayName}>
                <FadeIn>
                    <h2 className="text-lg font-semibold text-slate-800">Elegí un servicio</h2>
                    <div className="space-y-5 text-left">
                        {servicesByCategory.map((group) => (
                            <div key={group.name} className="space-y-2">
                                {servicesByCategory.length > 1 && (
                                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                                        {group.name}
                                    </h3>
                                )}
                                <div className="space-y-2">
                                    {group.services.map((service) => (
                                        <button
                                            key={service.id}
                                            type="button"
                                            onClick={() => handleSelectService(service)}
                                            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-sm transition-colors hover:border-brand-400 hover:bg-brand-50/40 active:bg-brand-50"
                                        >
                                            <div className="flex items-center justify-between gap-3">
                                                <span className="font-medium text-slate-800">{service.name}</span>
                                                <span className="whitespace-nowrap text-sm font-semibold text-brand-600">
                                                    {formatPrice(service.price)}
                                                </span>
                                            </div>
                                            <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                                                <span>{formatDuration(service.duration_minutes)}</span>
                                                {service.description && (
                                                    <>
                                                        <span aria-hidden="true">·</span>
                                                        <span className="truncate">{service.description}</span>
                                                    </>
                                                )}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ))}
                        {data.services.length === 0 && (
                            <p className="text-sm text-slate-500">
                                Este negocio todavía no publicó servicios para reservar online.
                            </p>
                        )}
                    </div>
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Profesional ──────────────────────────────────────── */
    if (step === 'professional' && selectedService) {
        return (
            <Shell businessName={displayName} onBack={() => goBackTo('service')}>
                <FadeIn>
                    <SelectionSummary service={selectedService} />
                    <h2 className="text-lg font-semibold text-slate-800">Elegí un profesional</h2>
                    {professionalsState === 'loading' ? (
                        <p className="text-sm text-slate-400 animate-pulse">Cargando profesionales…</p>
                    ) : professionalsState === 'error' ? (
                        <div className="space-y-3 text-left">
                            <ErrorBanner message="No pudimos cargar los profesionales." />
                            <button
                                type="button"
                                onClick={() => loadProfessionals(selectedService)}
                                className="w-full rounded-full border border-slate-300 bg-white px-6 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50"
                            >
                                Reintentar
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-2 text-left">
                            {professionals.map((professional) => (
                                <button
                                    key={professional.id}
                                    type="button"
                                    onClick={() => handleSelectProfessional(professional)}
                                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-sm transition-colors hover:border-brand-400 hover:bg-brand-50/40 active:bg-brand-50"
                                >
                                    <span className="font-medium text-slate-800">{professional.name}</span>
                                    {professional.description && (
                                        <p className="mt-0.5 text-xs text-slate-500">{professional.description}</p>
                                    )}
                                </button>
                            ))}
                        </div>
                    )}
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Fecha y horario ──────────────────────────────────── */
    if (step === 'datetime' && selectedService && professionalResolved) {
        return (
            <Shell
                businessName={displayName}
                onBack={() => goBackTo(professionals.length > 0 ? 'professional' : 'service')}
            >
                <FadeIn>
                    <SelectionSummary service={selectedService} professional={selectedProfessional} />
                    <h2 className="text-lg font-semibold text-slate-800">Elegí fecha y horario</h2>

                    <div className="text-left">
                        <span className="block text-xs font-medium text-slate-500" aria-hidden="true">
                            Fecha
                        </span>
                        <DatePicker
                            id="turno-date"
                            label="Fecha"
                            value={selectedDate}
                            onChange={handleSelectDate}
                            today={businessToday}
                            min={businessToday}
                            tone="brand"
                            formatValue={formatLongDate}
                            triggerClassName="mt-1 min-h-[44px] px-4 py-2.5"
                        />
                    </div>

                    {selectedDate && (
                        <div className="text-left">
                            {availabilityLoading ? (
                                <p className="text-sm text-slate-400 animate-pulse">Buscando horarios…</p>
                            ) : availabilityError ? (
                                <ErrorBanner message={availabilityError} />
                            ) : slots.length === 0 ? (
                                <p className="text-sm text-slate-500">
                                    No hay horarios disponibles para esta fecha. Probá con otro día.
                                </p>
                            ) : (
                                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                                    {slots.map((slot) => (
                                        <button
                                            key={slot.start}
                                            type="button"
                                            onClick={() => handleSelectSlot(slot)}
                                            className="rounded-lg border border-slate-200 bg-white py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-brand-400 hover:bg-brand-50/40 active:bg-brand-50"
                                        >
                                            {slot.start.slice(11, 16)}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Revisión + datos del cliente ───────────────────────── */
    if (step === 'review' && selectedService && selectedSlot && professionalResolved) {
        const canSubmit = customerName.trim().length >= 2 && customerPhone.trim().length >= 6 && !submitting;
        return (
            <Shell businessName={displayName} onBack={() => goBackTo('datetime')}>
                <FadeIn>
                    <h2 className="text-lg font-semibold text-slate-800">Revisá tu turno</h2>

                    <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                        <p className="font-semibold text-slate-800">{selectedService.name}</p>
                        {selectedProfessional && (
                            <p className="text-sm text-slate-600">{selectedProfessional.name}</p>
                        )}
                        <p className="text-sm text-slate-600">
                            {formatDateDisplay(selectedDate)} · {selectedSlot.start.slice(11, 16)}
                        </p>
                        <p className="text-sm text-slate-500">
                            {formatDuration(selectedService.duration_minutes)}
                        </p>
                    </div>

                    <div className="space-y-3 text-left">
                        <Field label="Nombre y apellido" htmlFor="customer-name">
                            <input
                                id="customer-name"
                                type="text"
                                value={customerName}
                                onChange={(e) => setCustomerName(e.target.value)}
                                className={inputClassName}
                                placeholder="Tu nombre"
                            />
                        </Field>
                        <Field label="Teléfono" htmlFor="customer-phone">
                            <input
                                id="customer-phone"
                                type="tel"
                                value={customerPhone}
                                onChange={(e) => setCustomerPhone(e.target.value)}
                                className={inputClassName}
                                placeholder="Tu teléfono"
                            />
                        </Field>
                        <Field label="Email (opcional)" htmlFor="customer-email">
                            <input
                                id="customer-email"
                                type="email"
                                value={customerEmail}
                                onChange={(e) => setCustomerEmail(e.target.value)}
                                className={inputClassName}
                                placeholder="tu@email.com"
                            />
                        </Field>
                    </div>

                    {submitError && <ErrorBanner message={submitError} />}

                    <button
                        type="button"
                        disabled={!canSubmit}
                        onClick={handleSubmitBooking}
                        className="w-full rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
                    >
                        {submitting ? 'Reservando…' : 'Continuar'}
                    </button>
                </FadeIn>
            </Shell>
        );
    }

    /* ── Estado de la reserva (sin seña, hold con seña, retorno de MP) ── */
    if (step === 'status' && bookingToken) {
        return (
            <Shell businessName={displayName}>
                <FadeIn>
                    <BookingStatus
                        key={bookingToken}
                        apiUrl={API_URL}
                        slug={slug}
                        publicToken={bookingToken}
                        initialBooking={booking}
                        paymentHint={returnHint}
                        onRestart={resetFlow}
                    />
                </FadeIn>
            </Shell>
        );
    }

    return null;
}

const inputClassName =
    'mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20';

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-xs font-medium text-slate-500" htmlFor={htmlFor}>
                {label}
            </label>
            {children}
        </div>
    );
}

/* ── Selection summary chip ──────────────────────────────────────── */

function SelectionSummary({
    service,
    professional,
}: {
    service: PublicAppointmentService;
    professional?: PublicAppointmentProfessional | null;
}) {
    return (
        <p className="text-xs text-slate-400">
            {service.name}
            {professional ? ` · ${professional.name}` : ''}
        </p>
    );
}

/* ── Layout shell ──────────────────────────────────────────────────── */

function Shell({
    businessName,
    onBack,
    children,
}: {
    businessName: string;
    onBack?: () => void;
    children: React.ReactNode;
}) {
    return (
        <div className="flex min-h-[100svh] flex-col bg-slate-50">
            <header className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
                <div
                    className="mb-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 ring-1 ring-brand-200/40"
                    aria-hidden="true"
                >
                    <CalendarIcon />
                </div>
                <h1 className="mt-2 text-xl font-semibold text-slate-900">{businessName}</h1>
                <p className="mt-1 text-sm text-slate-500">Reservá tu turno online</p>
            </header>

            <main className="flex flex-1 items-start justify-center px-3 py-2">
                <div className="w-full max-w-md rounded-2xl bg-white/80 p-6 shadow-md ring-1 ring-slate-200/70 backdrop-blur-sm space-y-5">
                    {onBack && (
                        <button
                            type="button"
                            onClick={onBack}
                            className="text-xs font-medium text-slate-400 hover:text-slate-600"
                        >
                            ← Volver
                        </button>
                    )}
                    {children}
                </div>
            </main>

            <footer className="mt-auto pb-6 pt-4 text-center text-[11px] text-slate-400">
                Impulsado por{' '}
                <Link href="/" className="font-semibold text-brand-600 transition-colors hover:underline">
                    MiRubro
                </Link>
            </footer>
        </div>
    );
}

function FadeIn({ children }: { children: React.ReactNode }) {
    return <div className="animate-fade-in space-y-5">{children}</div>;
}

function ErrorBanner({ message }: { message: string }) {
    return (
        <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-100">
            {message}
        </div>
    );
}

function CalendarIcon() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-7 w-7 text-brand-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
        </svg>
    );
}
