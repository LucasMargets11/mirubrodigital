import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

/**
 * PROD-02G1 — Recepcionista IA como producto independiente.
 *
 * El acceso comercial ya lo resolvió `/app/layout.tsx` (enforcement de la
 * suscripción principal) y el backend agrega `reception` a
 * `services.enabled` solo con una suscripción de Recepcionista con acceso
 * efectivo (`business/context.py`). Igual que `/app/turnos`, sin el producto
 * se vuelve al hub de servicios. Es UX: cada API conserva sus guards.
 */
export default async function RecepcionistaLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    if (!resolvedSession.services.enabled.includes('reception')) {
        redirect('/app/servicios');
    }

    return <section className="space-y-6">{children}</section>;
}
