"use client";

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, Calendar, Check, Edit, AlertCircle, TrendingUp, CheckCircle2, Clock } from 'lucide-react';
import { format, isPast, isToday, startOfMonth, subMonths } from 'date-fns';
import { es } from 'date-fns/locale';

import {
    listFixedExpenses,
    createFixedExpense,
    updateFixedExpense,
    getFixedExpensePeriods,
    payFixedExpensePeriod,
    listAccounts,
    FixedExpense,
    FixedExpensePeriod
} from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';
import { cn } from '@/lib/utils';

export function ExpensesClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [selectedFixed, setSelectedFixed] = useState<FixedExpense | null>(null);
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [isEditOpen, setIsEditOpen] = useState(false);
    const [payingPeriod, setPayingPeriod] = useState<FixedExpensePeriod | null>(null);

    const { data: fixedExpenses, isLoading } = useQuery({
        queryKey: ['treasury', 'fixed-expenses'],
        queryFn: listFixedExpenses,
    });

    const { data: periods, isLoading: periodsLoading } = useQuery({
        queryKey: ['treasury', 'fixed-expense-periods', selectedFixed?.id],
        queryFn: () => selectedFixed ? getFixedExpensePeriods(selectedFixed.id, {
            from: format(subMonths(startOfMonth(new Date()), 11), 'yyyy-MM-dd'),
            to: format(new Date(), 'yyyy-MM-dd')
        }) : Promise.resolve([]),
        enabled: !!selectedFixed,
    });

    const { data: accounts } = useQuery({
        queryKey: ['treasury', 'accounts'],
        queryFn: listAccounts
    });

    const createMutation = useMutation({
        mutationFn: createFixedExpense,
        onSuccess: (newFixed) => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'fixed-expenses'] });
            setIsCreateOpen(false);
            setSelectedFixed(newFixed);
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number, data: any }) => updateFixedExpense(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'fixed-expenses'] });
            setIsEditOpen(false);
        },
    });

    const payMutation = useMutation({
        mutationFn: ({ id, data }: { id: number, data: any }) => payFixedExpensePeriod(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'fixed-expense-periods'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'fixed-expenses'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setPayingPeriod(null);
        },
    });

    // Auto-select first fixed expense if none selected
    useMemo(() => {
        if (fixedExpenses && fixedExpenses.length > 0 && !selectedFixed) {
            setSelectedFixed(fixedExpenses[0]);
        }
    }, [fixedExpenses, selectedFixed]);

    const currentPeriod = useMemo(() => {
        if (!periods) return null;
        const currentMonth = format(new Date(), 'yyyy-MM');
        return periods.find(p => p.period_display === currentMonth);
    }, [periods]);

    if (isLoading) {
        return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;
    }

    if (!fixedExpenses || fixedExpenses.length === 0) {
        return (
            <>
                <EmptyState
                    title="No tenés gastos fijos registrados"
                    description="Los gastos fijos son aquellos que se repiten cada mes como Internet, Alquiler, Luz, etc. Creá tu primer gasto fijo para comenzar a llevar un control mensual."
                    actionLabel={canManage ? "Crear primer gasto fijo" : undefined}
                    onAction={() => setIsCreateOpen(true)}
                />
                {isCreateOpen && (
                    <FixedExpenseFormModal
                        isOpen={isCreateOpen}
                        onClose={() => setIsCreateOpen(false)}
                        onSubmit={(data) => createMutation.mutate(data)}
                        isLoading={createMutation.isPending}
                    />
                )}
            </>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center bg-white p-4 rounded-3xl border border-slate-200 shadow-sm">
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Gastos Fijos</h2>
                    <p className="text-sm text-slate-500">Gestión mensual de gastos recurrentes</p>
                </div>
                {canManage && (
                    <Button onClick={() => setIsCreateOpen(true)} className="rounded-full">
                        <Plus className="mr-2 h-4 w-4" />
                        Nuevo Gasto Fijo
                    </Button>
                )}
            </div>

            {/* Main Layout: Panel izquierdo + Panel derecho */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* LEFT PANEL: Lista de Gastos Fijos */}
                <div className="lg:col-span-1 space-y-3">
                    {fixedExpenses.map((fixed) => {
                        const isSelected = selectedFixed?.id === fixed.id;
                        const currentStatus = fixed.current_period_status?.status || 'not_created';
                        const isPaid = currentStatus === 'paid';
                        const isPending = currentStatus === 'pending';

                        return (
                            <button
                                key={fixed.id}
                                onClick={() => setSelectedFixed(fixed)}
                                className={cn(
                                    "w-full text-left bg-white rounded-2xl border-2 p-4 transition-all hover:shadow-md",
                                    isSelected ? "border-slate-900 shadow-md" : "border-slate-200"
                                )}
                            >
                                <div className="flex items-start justify-between mb-2">
                                    <h3 className="font-semibold text-slate-900">{fixed.name}</h3>
                                    {isPaid ? (
                                        <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                                    ) : isPending ? (
                                        <Clock className="h-5 w-5 text-amber-600 shrink-0" />
                                    ) : (
                                        <AlertCircle className="h-5 w-5 text-slate-400 shrink-0" />
                                    )}
                                </div>
                                <div className="flex items-baseline gap-2">
                                    {fixed.default_amount && (
                                        <span className="text-lg font-mono font-medium text-slate-700">
                                            <Currency amount={fixed.default_amount} />
                                        </span>
                                    )}
                                    {fixed.due_day && (
                                        <span className="text-xs text-slate-500">día {fixed.due_day}</span>
                                    )}
                                </div>
                                <div className="mt-2">
                                    <span className={cn(
                                        "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium",
                                        isPaid ? "bg-emerald-100 text-emerald-700" :
                                            isPending ? "bg-amber-100 text-amber-700" :
                                                "bg-slate-100 text-slate-600"
                                    )}>
                                        {isPaid ? "✓ Pago este mes" : isPending ? "⚠ Pendiente" : "Sin periodo"}
                                    </span>
                                </div>
                            </button>
                        );
                    })}
                </div>

                {/* RIGHT PANEL: Detalle del Gasto Fijo seleccionado */}
                <div className="lg:col-span-2">
                    {!selectedFixed ? (
                        <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center">
                            <p className="text-slate-500">Seleccioná un gasto fijo para ver su detalle</p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Header del gasto seleccionado */}
                            <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <h2 className="text-2xl font-bold text-slate-900">{selectedFixed.name}</h2>
                                        <div className="flex gap-4 mt-2 text-sm text-slate-600">
                                            {selectedFixed.default_amount && (
                                                <span>Monto: <strong><Currency amount={selectedFixed.default_amount} /></strong></span>
                                            )}
                                            {selectedFixed.due_day && (
                                                <span>Vencimiento: <strong>Día {selectedFixed.due_day}</strong></span>
                                            )}
                                        </div>
                                    </div>
                                    {canManage && (
                                        <Button variant="outline" size="sm" onClick={() => setIsEditOpen(true)}>
                                            <Edit className="h-4 w-4 mr-2" />
                                            Editar
                                        </Button>
                                    )}
                                </div>

                                {/* Estado del mes actual */}
                                {currentPeriod && (
                                    <div className={cn(
                                        "p-4 rounded-xl border-2",
                                        currentPeriod.status === 'paid' ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"
                                    )}>
                                        <div className="flex justify-between items-center">
                                            <div>
                                                <p className="text-sm font-medium text-slate-700">Mes actual - {format(new Date(), 'MMMM yyyy', { locale: es })}</p>
                                                <p className="text-2xl font-bold mt-1">
                                                    <Currency amount={currentPeriod.amount} />
                                                </p>
                                                {currentPeriod.status === 'paid' && currentPeriod.paid_at && (
                                                    <p className="text-sm text-slate-600 mt-1">
                                                        Pagado el {format(new Date(currentPeriod.paid_at), 'dd/MM/yyyy')}
                                                    </p>
                                                )}
                                            </div>
                                            {currentPeriod.status === 'pending' && canManage && (
                                                <Button onClick={() => setPayingPeriod(currentPeriod)}>
                                                    <Check className="mr-2 h-4 w-4" />
                                                    Pagar
                                                </Button>
                                            )}
                                            {currentPeriod.status === 'paid' && (
                                                <div className="flex items-center gap-2 text-emerald-700">
                                                    <CheckCircle2 className="h-6 w-6" />
                                                    <span className="font-medium">Pagado</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Histórico de periodos */}
                            <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-sm">
                                <div className="p-6 border-b border-slate-200">
                                    <h3 className="font-semibold text-slate-900">Historial de Pagos</h3>
                                    <p className="text-sm text-slate-500">Últimos 12 meses</p>
                                </div>

                                {periodsLoading ? (
                                    <div className="p-12 flex justify-center">
                                        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                                    </div>
                                ) : !periods || periods.length === 0 ? (
                                    <div className="p-12 text-center text-slate-500">
                                        <p>No hay historial de periodos para este gasto</p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-slate-200">
                                        {periods.map((period) => (
                                            <div key={period.id} className="p-4 hover:bg-slate-50 transition-colors">
                                                <div className="flex justify-between items-center">
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-3">
                                                            <p className="font-medium text-slate-900">
                                                                {format(new Date(period.period + '-15'), 'MMMM yyyy', { locale: es })}
                                                            </p>
                                                            <span className={cn(
                                                                "text-xs px-2 py-0.5 rounded-full font-medium",
                                                                period.status === 'paid' ? "bg-emerald-100 text-emerald-700" :
                                                                    period.status === 'pending' ? "bg-amber-100 text-amber-700" :
                                                                        "bg-slate-100 text-slate-600"
                                                            )}>
                                                                {period.status === 'paid' ? 'Pagado' : period.status === 'pending' ? 'Pendiente' : 'Omitido'}
                                                            </span>
                                                        </div>
                                                        {period.due_date && (
                                                            <p className="text-sm text-slate-500 mt-1">
                                                                Vencimiento: {format(new Date(period.due_date), 'dd/MM/yyyy')}
                                                            </p>
                                                        )}
                                                        {period.paid_at && (
                                                            <p className="text-sm text-slate-600 mt-1">
                                                                Pagado el {format(new Date(period.paid_at), 'dd/MM/yyyy')}
                                                                {period.paid_account_name && ` via ${period.paid_account_name}`}
                                                            </p>
                                                        )}
                                                    </div>
                                                    <div className="text-right">
                                                        <p className="text-lg font-mono font-semibold text-slate-900">
                                                            <Currency amount={period.amount} />
                                                        </p>
                                                        {period.status === 'pending' && canManage && (
                                                            <Button
                                                                variant="outline"
                                                                size="sm"
                                                                className="mt-2"
                                                                onClick={() => setPayingPeriod(period)}
                                                            >
                                                                Pagar
                                                            </Button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Modals */}
            {isCreateOpen && (
                <FixedExpenseFormModal
                    isOpen={isCreateOpen}
                    onClose={() => setIsCreateOpen(false)}
                    onSubmit={(data) => createMutation.mutate(data)}
                    isLoading={createMutation.isPending}
                />
            )}

            {isEditOpen && selectedFixed && (
                <FixedExpenseFormModal
                    isOpen={isEditOpen}
                    fixedExpense={selectedFixed}
                    onClose={() => setIsEditOpen(false)}
                    onSubmit={(data) => updateMutation.mutate({ id: selectedFixed.id, data })}
                    isLoading={updateMutation.isPending}
                />
            )}

            {payingPeriod && accounts && (
                <PayPeriodModal
                    isOpen={!!payingPeriod}
                    period={payingPeriod}
                    accounts={accounts}
                    onClose={() => setPayingPeriod(null)}
                    onSubmit={(data) => payMutation.mutate({ id: payingPeriod.id, data })}
                    isLoading={payMutation.isPending}
                />
            )}
        </div>
    );
}

function FixedExpenseFormModal({ isOpen, onClose, onSubmit, isLoading, fixedExpense }: any) {
    const [name, setName] = useState(fixedExpense?.name || '');
    const [defaultAmount, setDefaultAmount] = useState(fixedExpense?.default_amount || '');
    const [dueDay, setDueDay] = useState(fixedExpense?.due_day || '');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({
            name,
            default_amount: defaultAmount ? parseFloat(defaultAmount) : undefined,
            due_day: dueDay ? parseInt(dueDay) : undefined,
        });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title={fixedExpense ? "Editar Gasto Fijo" : "Nuevo Gasto Fijo"}>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Nombre del gasto</label>
                    <input
                        autoFocus
                        required
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        placeholder="Ej: Internet, Alquiler, Luz..."
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Monto por defecto (opcional)</label>
                    <input
                        type="number"
                        step="0.01"
                        value={defaultAmount}
                        onChange={e => setDefaultAmount(e.target.value)}
                        placeholder="0.00"
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border font-mono"
                    />
                    <p className="text-xs text-slate-500 mt-1">Monto que se usará por defecto cada mes</p>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Día de vencimiento (opcional)</label>
                    <input
                        type="number"
                        min="1"
                        max="28"
                        value={dueDay}
                        onChange={e => setDueDay(e.target.value)}
                        placeholder="1-28"
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                    />
                    <p className="text-xs text-slate-500 mt-1">Día del mes en que vence (1-28)</p>
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {fixedExpense ? 'Actualizar' : 'Crear'}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}

function PayPeriodModal({ isOpen, onClose, onSubmit, isLoading, accounts, period }: any) {
    const [accountId, setAccountId] = useState('');
    const [amount, setAmount] = useState(period.amount);
    const [paidAt, setPaidAt] = useState(format(new Date(), 'yyyy-MM-dd'));

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({
            account_id: Number(accountId),
            amount: parseFloat(amount),
            paid_at: paidAt
        });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title={`Pagar: ${period.fixed_expense_name}`}>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="p-4 bg-slate-50 rounded-md">
                    <p className="text-sm text-slate-500">Periodo</p>
                    <p className="text-lg font-bold text-slate-900">
                        {format(new Date(period.period + '-15'), 'MMMM yyyy', { locale: es })}
                    </p>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Cuenta de pago</label>
                    <select
                        required
                        value={accountId}
                        onChange={e => setAccountId(e.target.value)}
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                    >
                        <option value="">Seleccionar cuenta...</option>
                        {accounts.filter((a: any) => a.is_active).map((a: any) => (
                            <option key={a.id} value={a.id}>{a.name} ({a.type})</option>
                        ))}
                    </select>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Monto</label>
                    <input
                        required
                        type="number"
                        step="0.01"
                        value={amount}
                        onChange={e => setAmount(e.target.value)}
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border font-mono text-lg"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Fecha de pago</label>
                    <input
                        required
                        type="date"
                        value={paidAt}
                        onChange={e => setPaidAt(e.target.value)}
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                    />
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Confirmar Pago
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
