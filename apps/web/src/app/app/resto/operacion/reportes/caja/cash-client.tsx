'use client';

import { CashSessionsList, cashSessionStatusOptions } from '@/modules/reports/cash/cash-sessions-list';

export function RestauranteCashReportsClient() {
    return (
        <CashSessionsList
            eyebrow="Caja restaurante"
            title="Sesiones de caja"
            description="Controlá aperturas, cierres y diferencias de tus puntos de venta."
            detailHref={(id) => `/app/resto/operacion/reportes/caja/${id}`}
            exportFilePrefix="resto-cajas"
            filtersConfig={{
                showStatus: true,
                statusOptions: cashSessionStatusOptions,
                defaultStatus: 'all',
                showSearch: true,
                searchPlaceholder: 'Buscar por caja o usuario',
            }}
            ctaLabel="Ver detalle"
        />
    );
}
