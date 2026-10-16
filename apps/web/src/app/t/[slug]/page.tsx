import { cache } from 'react';
import { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl } from '@/lib/api-url';
import type { PublicAppointmentBusiness } from '@/features/appointments/types';
import { parsePaymentHint } from '@/features/appointments/public-booking';
import { TurnosFlowClient } from './turnos-flow-client';

// Datos siempre frescos: servicios/profesionales activos pueden cambiar.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

type Props = {
    params: Promise<{ slug: string }>;
    // Back URLs de Mercado Pago (Slice 6C): `?booking=<public_token>&payment=...`.
    searchParams: Promise<{ booking?: string | string[]; payment?: string | string[] }>;
};

function firstParam(value: string | string[] | undefined): string | null {
    const first = Array.isArray(value) ? value[0] : value;
    return first ? first : null;
}

const getPublicBusiness = cache(async (slug: string) => {
    const apiBase = getServerApiBaseUrl();
    const res = await fetch(`${apiBase}/api/v1/appointments/public/${slug}/`, {
        cache: 'no-store',
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicAppointmentBusiness;
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { slug } = await params;
    const data = await getPublicBusiness(slug);
    if (!data) {
        return { title: 'Turnos no disponibles' };
    }
    return {
        title: `Reservar turno — ${data.business.name}`,
        description: `Elegí un servicio y horario disponible en ${data.business.name}.`,
    };
}

export default async function PublicTurnosPage({ params, searchParams }: Props) {
    const { slug } = await params;
    const query = await searchParams;
    const data = await getPublicBusiness(slug);

    if (!data) {
        notFound();
    }

    return (
        <TurnosFlowClient
            slug={slug}
            data={data}
            initialBookingToken={firstParam(query.booking)}
            paymentHint={parsePaymentHint(firstParam(query.payment))}
        />
    );
}
