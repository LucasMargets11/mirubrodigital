"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Save, Loader2, CreditCard, Building2, Wallet, Smartphone, HelpCircle } from 'lucide-react';
import { getTreasurySettings, updateTreasurySettings, listAccounts, TreasurySettings } from '@/lib/api/treasury';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const ACCOUNT_FIELDS: Array<{
    key: keyof TreasurySettings;
    label: string;
    description: string;
    icon: React.ReactNode;
}> = [
    {
        key: 'default_cash_account',
        label: 'Cuenta para Efectivo',
        description: 'Ventas pagadas en efectivo se registran aquí',
        icon: <Wallet className="h-5 w-5" />,
    },
    {
        key: 'default_bank_account',
        label: 'Cuenta para Transferencia Bancaria',
        description: 'Ventas por transferencia bancaria',
        icon: <Building2 className="h-5 w-5" />,
    },
    {
        key: 'default_mercadopago_account',
        label: 'Cuenta para MercadoPago / QR',
        description: 'Cobros mediante MercadoPago o código QR',
        icon: <Smartphone className="h-5 w-5" />,
    },
    {
        key: 'default_card_account',
        label: 'Cuenta para Tarjeta',
        description: 'Ventas con tarjeta de débito/crédito',
        icon: <CreditCard className="h-5 w-5" />,
    },
    {
        key: 'default_other_account',
        label: 'Cuenta para Otros medios',
        description: 'Cualquier otro método de pago no categorizado',
        icon: <HelpCircle className="h-5 w-5" />,
    },
    {
        key: 'default_income_account',
        label: 'Cuenta de Ingresos (manual)',
        description: 'Ingresos manuales sin medio de pago específico',
        icon: <Building2 className="h-5 w-5" />,
    },
    {
        key: 'default_expense_account',
        label: 'Cuenta de Egresos (manual)',
        description: 'Gastos manuales por defecto',
        icon: <Wallet className="h-5 w-5" />,
    },
    {
        key: 'default_payroll_account',
        label: 'Cuenta para Sueldos',
        description: 'Desde dónde se descuenta el pago de sueldos',
        icon: <CreditCard className="h-5 w-5" />,
    },
];

export function TreasurySettingsClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [savedOk, setSavedOk] = useState(false);

    const { data: settings, isLoading: settingsLoading } = useQuery({
        queryKey: ['treasury', 'settings'],
        queryFn: getTreasurySettings,
    });

    const { data: accounts, isLoading: accountsLoading } = useQuery({
        queryKey: ['treasury', 'accounts'],
        queryFn: listAccounts,
    });

    const [form, setForm] = useState<Partial<TreasurySettings>>({});

    const updateMutation = useMutation({
        mutationFn: updateTreasurySettings,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'settings'] });
            setSavedOk(true);
            setTimeout(() => setSavedOk(false), 3000);
        },
    });

    const currentValue = (key: keyof TreasurySettings): string => {
        const formVal = form[key];
        if (formVal !== undefined) return String(formVal ?? '');
        const settingsVal = settings?.[key];
        return String(settingsVal ?? '');
    };

    const handleChange = (key: keyof TreasurySettings, value: string) => {
        setForm(prev => ({ ...prev, [key]: value ? Number(value) : null }));
    };

    const handleSave = () => {
        updateMutation.mutate(form);
    };

    const isLoading = settingsLoading || accountsLoading;
    const activeAccounts = accounts?.filter(a => a.is_active) ?? [];

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-slate-100">
                    <Settings className="h-6 w-6 text-slate-700" />
                </div>
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Configuración de Tesorería</h2>
                    <p className="text-sm text-slate-500">Definí a qué cuenta se acredita cada tipo de ingreso automáticamente</p>
                </div>
            </div>

            {isLoading ? (
                <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
            ) : (
                <div className="space-y-3">
                    {ACCOUNT_FIELDS.map(({ key, label, description, icon }) => (
                        <div key={key} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                            <div className="flex items-start justify-between gap-4">
                                <div className="flex items-start gap-3">
                                    <div className="p-2 rounded-xl bg-slate-100 text-slate-600 mt-0.5">
                                        {icon}
                                    </div>
                                    <div>
                                        <p className="font-medium text-slate-900 text-sm">{label}</p>
                                        <p className="text-xs text-slate-500 mt-0.5">{description}</p>
                                    </div>
                                </div>
                                <select
                                    value={currentValue(key)}
                                    onChange={e => handleChange(key, e.target.value)}
                                    disabled={!canManage}
                                    className={cn(
                                        "rounded-xl border border-slate-200 text-sm p-2 min-w-[200px] bg-white",
                                        !canManage && "opacity-60 cursor-not-allowed"
                                    )}
                                >
                                    <option value="">— Sin asignar —</option>
                                    {activeAccounts.map(a => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {canManage && (
                <div className="flex items-center justify-end gap-3">
                    {savedOk && (
                        <span className="text-sm text-emerald-600 font-medium">✓ Configuración guardada</span>
                    )}
                    {updateMutation.isError && (
                        <span className="text-sm text-rose-600">Error al guardar. Intentá de nuevo.</span>
                    )}
                    <Button
                        onClick={handleSave}
                        disabled={updateMutation.isPending || Object.keys(form).length === 0}
                    >
                        {updateMutation.isPending
                            ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Guardando...</>
                            : <><Save className="mr-2 h-4 w-4" />Guardar cambios</>
                        }
                    </Button>
                </div>
            )}
        </div>
    );
}
