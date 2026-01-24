'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { ToastBubble } from '@/components/app/toast';
import { useCommercialSettingsQuery, useUpdateCommercialSettingsMutation } from '@/features/gestion/hooks';
import type { CommercialSettings } from '@/features/gestion/types';
import { cn } from '@/lib/utils';

type BooleanSettingKey =
    | 'allow_sell_without_stock'
    | 'block_sales_if_no_open_cash_session'
    | 'require_customer_for_sales'
    | 'allow_negative_price_or_discount'
    | 'warn_on_low_stock_threshold_enabled'
    | 'enable_sales_notes'
    | 'enable_receipts';

type ToastState = { message: string; tone: 'success' | 'error' };

type ToggleDescriptor = {
    key: BooleanSettingKey;
    label: string;
    description: string;
    value: boolean;
};

type SettingsCardProps = {
    title: string;
    description: string;
    items: ToggleDescriptor[];
    pendingFields: Record<string, boolean>;
    onToggle: (field: BooleanSettingKey, value: boolean) => void;
    extraContent?: ReactNode;
};

export function GestionSettingsClient() {
    const settingsQuery = useCommercialSettingsQuery();
    const updateSettings = useUpdateCommercialSettingsMutation();
    const [thresholdDraft, setThresholdDraft] = useState('5');
    const [pendingFields, setPendingFields] = useState<Record<string, boolean>>({});
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        if (settingsQuery.data) {
            setThresholdDraft(String(settingsQuery.data.low_stock_threshold_default));
        }
    }, [settingsQuery.data]);

    useEffect(() => {
        return () => {
            if (toastTimeoutRef.current) {
                clearTimeout(toastTimeoutRef.current);
            }
        };
    }, []);

    const settings = settingsQuery.data;

    const setFieldPending = (field: string, isPending: boolean) => {
        setPendingFields((prev) => {
            if (isPending) {
                return { ...prev, [field]: true };
            }
            const next = { ...prev };
            delete next[field];
            return next;
        });
    };

    const showToast = (message: string, tone: 'success' | 'error' = 'success') => {
        if (toastTimeoutRef.current) {
            clearTimeout(toastTimeoutRef.current);
        }
        setToast({ message, tone });
        toastTimeoutRef.current = setTimeout(() => setToast(null), 2600);
    };

    const handleUpdate = async (changes: Partial<CommercialSettings>, field: string) => {
        setFieldPending(field, true);
        try {
            await updateSettings.mutateAsync(changes);
            showToast('Guardado');
        } catch (error) {
            console.error(error);
            showToast('No pudimos guardar los cambios', 'error');
        } finally {
            setFieldPending(field, false);
        }
    };

    const handleThresholdBlur = () => {
        if (!settings) {
            return;
        }
        const numericValue = Math.max(0, Number(thresholdDraft) || 0);
        if (numericValue === settings.low_stock_threshold_default) {
            if (thresholdDraft !== String(numericValue)) {
                setThresholdDraft(String(numericValue));
            }
            return;
        }
        handleUpdate({ low_stock_threshold_default: numericValue }, 'low_stock_threshold_default');
    };

    const lowStockInputDisabled = useMemo(() => {
        return !settings?.warn_on_low_stock_threshold_enabled;
    }, [settings]);

    return (
        <section className="space-y-6">
            <header className="space-y-1">
                <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Gestión Comercial</p>
                <h1 className="text-3xl font-display font-semibold text-slate-900">Configuración</h1>
                <p className="text-base text-slate-500">
                    Ajustá reglas de stock, validaciones y comprobantes por negocio. Los cambios impactan de inmediato.
                </p>
            </header>

            {settingsQuery.isError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    <div className="flex items-center justify-between gap-3">
                        <p>No pudimos cargar la configuración actual.</p>
                        <button
                            type="button"
                            onClick={() => settingsQuery.refetch()}
                            className="rounded-full border border-rose-300 px-4 py-1 text-xs font-semibold text-rose-700 hover:border-rose-500"
                        >
                            Reintentar
                        </button>
                    </div>
                </div>
            )}

            {settingsQuery.isLoading && <SettingsSkeleton />}

            {!settingsQuery.isLoading && settings && (
                <div className="space-y-6">
                    <SettingsCard
                        title="Stock y ventas"
                        description="Define cómo los movimientos de stock reaccionan a cada venta."
                        items={[
                            {
                                key: 'allow_sell_without_stock',
                                label: 'Permitir vender productos sin stock',
                                description: 'Si está desactivado, el sistema bloqueará ventas con stock insuficiente.',
                                value: settings.allow_sell_without_stock,
                            },
                            {
                                key: 'block_sales_if_no_open_cash_session',
                                label: 'Bloquear ventas si no hay caja abierta',
                                description: 'Recomendado para operar sólo desde Caja. El equipo verá un aviso para abrirla.',
                                value: settings.block_sales_if_no_open_cash_session,
                            },
                            {
                                key: 'warn_on_low_stock_threshold_enabled',
                                label: 'Mostrar alertas de stock bajo',
                                description: 'Activa chips y avisos cuando un producto baja del umbral configurado.',
                                value: settings.warn_on_low_stock_threshold_enabled,
                            },
                        ]}
                        pendingFields={pendingFields}
                        onToggle={(field, value) => handleUpdate({ [field]: value } as Partial<CommercialSettings>, field)}
                        extraContent={
                            <ThresholdField
                                value={thresholdDraft}
                                onChange={setThresholdDraft}
                                onBlur={handleThresholdBlur}
                                disabled={lowStockInputDisabled || Boolean(pendingFields.low_stock_threshold_default)}
                                loading={Boolean(pendingFields.low_stock_threshold_default)}
                            />
                        }
                    />

                    <SettingsCard
                        title="Validaciones"
                        description="Indica qué datos son obligatorios durante la venta."
                        items={[
                            {
                                key: 'require_customer_for_sales',
                                label: 'Requerir cliente para vender',
                                description: 'Sólo permitirá registrar ventas cuando se seleccione un cliente.',
                                value: settings.require_customer_for_sales,
                            },
                            {
                                key: 'allow_negative_price_or_discount',
                                label: 'Permitir precios/desc. negativos',
                                description: 'Útil para notas de crédito o ajustes. Desactivalo para evitar descuentos excesivos.',
                                value: settings.allow_negative_price_or_discount,
                            },
                        ]}
                        pendingFields={pendingFields}
                        onToggle={(field, value) => handleUpdate({ [field]: value } as Partial<CommercialSettings>, field)}
                    />

                    <SettingsCard
                        title="Comprobantes y notas"
                        description="Controla qué elementos se muestran en el checkout."
                        items={[
                            {
                                key: 'enable_sales_notes',
                                label: 'Habilitar notas en ventas',
                                description: 'Muestra el campo de notas internas cuando se genera una venta.',
                                value: settings.enable_sales_notes,
                            },
                            {
                                key: 'enable_receipts',
                                label: 'Habilitar comprobantes/tickets',
                                description: 'Activa los accesos directos para emitir tickets o facturas rápidas.',
                                value: settings.enable_receipts,
                            },
                        ]}
                        pendingFields={pendingFields}
                        onToggle={(field, value) => handleUpdate({ [field]: value } as Partial<CommercialSettings>, field)}
                    />
                </div>
            )}

            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </section>
    );
}

function SettingsCard({ title, description, items, pendingFields, onToggle, extraContent }: SettingsCardProps) {
    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm">
            <header className="space-y-1">
                <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
                <p className="text-sm text-slate-500">{description}</p>
            </header>
            <div className="space-y-5">
                {items.map((item) => (
                    <SettingToggleRow
                        key={item.key}
                        label={item.label}
                        description={item.description}
                        checked={item.value}
                        disabled={Boolean(pendingFields[item.key])}
                        loading={Boolean(pendingFields[item.key])}
                        onChange={(value) => onToggle(item.key, value)}
                    />
                ))}
            </div>
            {extraContent}
        </section>
    );
}

function SettingToggleRow({
    label,
    description,
    checked,
    disabled,
    loading,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    disabled?: boolean;
    loading?: boolean;
    onChange: (value: boolean) => void;
}) {
    return (
        <div className="flex items-start justify-between gap-4">
            <div className="max-w-2xl">
                <p className="font-medium text-slate-900">{label}</p>
                <p className="text-sm text-slate-500">{description}</p>
            </div>
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                onClick={() => onChange(!checked)}
                disabled={disabled}
                className={cn(
                    'flex h-8 w-14 items-center rounded-full border transition disabled:cursor-not-allowed disabled:opacity-60',
                    checked ? 'border-slate-900 bg-slate-900' : 'border-slate-300 bg-slate-100'
                )}
            >
                <span
                    className={cn(
                        'ml-1 inline-flex h-6 w-6 transform items-center justify-center rounded-full bg-white text-[10px] font-semibold text-slate-500 transition',
                        checked ? 'translate-x-5' : 'translate-x-0'
                    )}
                >
                    {loading ? '…' : checked ? 'ON' : 'OFF'}
                </span>
            </button>
        </div>
    );
}

function ThresholdField({
    value,
    onChange,
    onBlur,
    disabled,
    loading,
}: {
    value: string;
    onChange: (value: string) => void;
    onBlur: () => void;
    disabled?: boolean;
    loading?: boolean;
}) {
    return (
        <div className="flex flex-col gap-1 rounded-2xl border border-slate-100 bg-slate-50 p-4 text-sm text-slate-600">
            <label className="text-xs font-semibold text-slate-500">Umbral de stock bajo por defecto</label>
            <div className="flex items-center gap-3">
                <input
                    type="number"
                    min={0}
                    value={value}
                    disabled={disabled}
                    onChange={(event) => onChange(event.target.value)}
                    onBlur={onBlur}
                    className="w-32 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-slate-900 focus:outline-none disabled:cursor-not-allowed"
                />
                {loading && <span className="text-xs text-slate-400">Guardando…</span>}
            </div>
            <p className="text-xs text-slate-500">Se usa como valor sugerido para nuevos productos y alertas de stock.</p>
        </div>
    );
}

function SettingsSkeleton() {
    return (
        <div className="grid gap-6">
            {[0, 1, 2].map((index) => (
                <div key={index} className="space-y-4 rounded-3xl border border-slate-100 bg-white/80 p-6">
                    <div className="space-y-2">
                        <div className="h-4 w-44 animate-pulse rounded-full bg-slate-200" />
                        <div className="h-3 w-64 animate-pulse rounded-full bg-slate-100" />
                    </div>
                    <div className="space-y-3">
                        {[0, 1, 2].map((item) => (
                            <div key={item} className="flex items-center justify-between">
                                <div className="space-y-2">
                                    <div className="h-3 w-56 animate-pulse rounded-full bg-slate-100" />
                                    <div className="h-3 w-40 animate-pulse rounded-full bg-slate-100" />
                                </div>
                                <div className="h-8 w-14 animate-pulse rounded-full bg-slate-200" />
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
}
