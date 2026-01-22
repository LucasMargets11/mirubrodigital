'use client';

import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getRegisters } from '@/features/cash/api';

export type ReportsFiltersValue = {
    preset: string;
    from: string;
    to: string;
    groupBy?: 'day' | 'week' | 'month';
    status?: string;
    paymentMethod?: string;
    method?: string;
    userId?: string;
    registerId?: string;
};

type ReportsFiltersProps = {
    value: ReportsFiltersValue;
    onChange: (value: ReportsFiltersValue) => void;
    showGroupBy?: boolean;
    showStatus?: boolean;
    showPaymentMethod?: boolean;
    showMethod?: boolean;
    showUser?: boolean;
    showRegister?: boolean;
};

const presetDefinitions: Array<{
    key: string;
    label: string;
    getRange: () => { from: string; to: string };
}> = [
        {
            key: 'today',
            label: 'Hoy',
            getRange: () => {
                const today = new Date();
                return { from: formatDate(today), to: formatDate(today) };
            },
        },
        {
            key: 'yesterday',
            label: 'Ayer',
            getRange: () => {
                const date = new Date();
                date.setDate(date.getDate() - 1);
                return { from: formatDate(date), to: formatDate(date) };
            },
        },
        {
            key: 'last7',
            label: '7 días',
            getRange: () => {
                const to = new Date();
                const from = new Date();
                from.setDate(to.getDate() - 6);
                return { from: formatDate(from), to: formatDate(to) };
            },
        },
        {
            key: 'last30',
            label: '30 días',
            getRange: () => {
                const to = new Date();
                const from = new Date();
                from.setDate(to.getDate() - 29);
                return { from: formatDate(from), to: formatDate(to) };
            },
        },
        {
            key: 'mtd',
            label: 'Mes actual',
            getRange: () => {
                const to = new Date();
                const from = new Date(to.getFullYear(), to.getMonth(), 1);
                return { from: formatDate(from), to: formatDate(to) };
            },
        },
        {
            key: 'last_month',
            label: 'Mes anterior',
            getRange: () => {
                const ref = new Date();
                const from = new Date(ref.getFullYear(), ref.getMonth() - 1, 1);
                const to = new Date(ref.getFullYear(), ref.getMonth(), 0);
                return { from: formatDate(from), to: formatDate(to) };
            },
        },
    ];

function formatDate(date: Date) {
    return date.toISOString().slice(0, 10);
}

export function ReportsFilters({
    value,
    onChange,
    showGroupBy,
    showStatus,
    showPaymentMethod,
    showMethod,
    showUser,
    showRegister,
}: ReportsFiltersProps) {
    const { data: registers } = useQuery({
        queryKey: ['cash', 'registers'],
        queryFn: getRegisters,
    });

    const selectedPreset = value.preset ?? 'last7';

    const handlePresetChange = useCallback(
        (key: string) => {
            const preset = presetDefinitions.find((item) => item.key === key);
            if (!preset) {
                return;
            }
            const range = preset.getRange();
            onChange({ ...value, preset: key, from: range.from, to: range.to });
        },
        [onChange, value],
    );

    const handleDateChange = useCallback(
        (field: 'from' | 'to', dateValue: string) => {
            onChange({ ...value, preset: 'custom', [field]: dateValue });
        },
        [onChange, value],
    );

    const registerOptions = useMemo(() => registers ?? [], [registers]);

    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white/90 p-4 shadow-sm">
            <div className="flex flex-wrap gap-2">
                {presetDefinitions.map((preset) => (
                    <button
                        key={preset.key}
                        type="button"
                        onClick={() => handlePresetChange(preset.key)}
                        className={`rounded-full px-4 py-2 text-sm font-medium transition ${selectedPreset === preset.key
                            ? 'bg-slate-900 text-white'
                            : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:text-slate-900'
                            }`}
                    >
                        {preset.label}
                    </button>
                ))}
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <label className="text-sm text-slate-600">
                    Desde
                    <input
                        type="date"
                        value={value.from}
                        onChange={(event) => handleDateChange('from', event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400 focus:outline-none"
                    />
                </label>
                <label className="text-sm text-slate-600">
                    Hasta
                    <input
                        type="date"
                        value={value.to}
                        onChange={(event) => handleDateChange('to', event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400 focus:outline-none"
                    />
                </label>
                {showGroupBy && (
                    <label className="text-sm text-slate-600">
                        Agrupar por
                        <select
                            value={value.groupBy ?? 'day'}
                            onChange={(event) => onChange({ ...value, groupBy: event.target.value as ReportsFiltersValue['groupBy'] })}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400"
                        >
                            <option value="day">Día</option>
                            <option value="week">Semana</option>
                            <option value="month">Mes</option>
                        </select>
                    </label>
                )}
                {showStatus && (
                    <label className="text-sm text-slate-600">
                        Estado
                        <select
                            value={value.status ?? ''}
                            onChange={(event) => onChange({ ...value, status: event.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400"
                        >
                            <option value="">Todos</option>
                            <option value="completed">Completadas</option>
                            <option value="cancelled">Canceladas</option>
                        </select>
                    </label>
                )}
                {showPaymentMethod && (
                    <label className="text-sm text-slate-600">
                        Método de pago
                        <select
                            value={value.paymentMethod ?? ''}
                            onChange={(event) => onChange({ ...value, paymentMethod: event.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400"
                        >
                            <option value="">Todos</option>
                            <option value="cash">Efectivo</option>
                            <option value="card">Tarjeta</option>
                            <option value="transfer">Transferencia</option>
                            <option value="wallet">Billetera</option>
                            <option value="account">Cuenta corriente</option>
                            <option value="other">Otros</option>
                        </select>
                    </label>
                )}
                {showMethod && (
                    <label className="text-sm text-slate-600">
                        Operación
                        <select
                            value={value.method ?? ''}
                            onChange={(event) => onChange({ ...value, method: event.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400"
                        >
                            <option value="">Todos</option>
                            <option value="cash">Efectivo</option>
                            <option value="debit">Débito</option>
                            <option value="credit">Crédito</option>
                            <option value="transfer">Transferencia</option>
                            <option value="wallet">Billetera</option>
                            <option value="account">Cuenta corriente</option>
                        </select>
                    </label>
                )}
                {showRegister && (
                    <label className="text-sm text-slate-600">
                        Caja
                        <select
                            value={value.registerId ?? ''}
                            onChange={(event) => onChange({ ...value, registerId: event.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400"
                        >
                            <option value="">Todas</option>
                            {registerOptions.map((register) => (
                                <option key={register.id} value={register.id}>
                                    {register.name}
                                </option>
                            ))}
                        </select>
                    </label>
                )}
                {showUser && (
                    <label className="text-sm text-slate-600">
                        Usuario
                        <input
                            type="text"
                            value={value.userId ?? ''}
                            onChange={(event) => onChange({ ...value, userId: event.target.value })}
                            placeholder="ID, email o nombre"
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-900 shadow-inner focus:border-slate-400 focus:outline-none"
                        />
                    </label>
                )}
            </div>
        </section>
    );
}
