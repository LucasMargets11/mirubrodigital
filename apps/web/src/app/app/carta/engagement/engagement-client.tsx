'use client';

import { EngagementSettingsSection } from '@/components/app/engagement-settings-section';

export function EngagementPageClient() {
    return (
        <div className="p-6 space-y-6 animate-in fade-in">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Propinas y Reseñas</h1>
                <p className="text-sm text-slate-500 mt-1">
                    Configurá propinas con Mercado Pago y reseñas de Google para que tus clientes puedan dejarte feedback desde la carta.
                </p>
            </div>

            <EngagementSettingsSection />
        </div>
    );
}
