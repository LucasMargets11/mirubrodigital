'use client';

import { CashSessionsList, cashSessionStatusOptions } from '@/modules/reports/cash/cash-sessions-list';

export function CashReportsClient() {
    return (
        <CashSessionsList
            eyebrow="Caja"
            title="Cierres y arqueos"
            description="Arqueá tus cajas y encontrá diferencias en segundos."
            detailHref={(id) => `/app/gestion/reportes/caja/${id}`}
            exportFilePrefix="cierres-caja"
            filtersConfig={{
                showRegister: true,
                showUser: true,
                defaultStatus: 'closed',
                statusOptions: cashSessionStatusOptions,
            }}
            ctaLabel="Ver"
        />
    );
}
