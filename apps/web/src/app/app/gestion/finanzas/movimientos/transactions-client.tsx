"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    ArrowLeftRight, Loader2, Search, ArrowDownCircle, ArrowUpCircle, CheckCircle2,
    Receipt, Users, RotateCcw, FileText, TrendingDown, TrendingUp, Repeat,
    Plus, Download, Ban, ChevronLeft, ChevronRight, AlertTriangle, ShoppingCart
} from 'lucide-react';
import { format } from 'date-fns';
import { formatDateTimeAR, todayDateString } from '@/lib/dates';

import {
    listTransactions, listAccounts, listCategories, transferFunds,
    createTransaction, voidTransaction, getTransactionsCsvUrl, TransactionParams,
    TreasuryTransaction
} from '@/lib/api/treasury';
import Link from 'next/link';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 50;

export function TransactionsClient({ canManage, initialDateFrom, initialDateTo }: { canManage: boolean; initialDateFrom: string; initialDateTo: string }) {
    const queryClient = useQueryClient();
    const [isTransferOpen, setIsTransferOpen] = useState(false);
    const [isNewTxnOpen, setIsNewTxnOpen] = useState(false);
    const [voidingTxn, setVoidingTxn] = useState<TreasuryTransaction | null>(null);
    const [offset, setOffset] = useState(0);

    const [filters, setFilters] = useState<TransactionParams>({
        search: '',
        account: '',
        category: '',
        direction: '',
        date_from: initialDateFrom,
        date_to: initialDateTo,
    });

    const queryFilters = { ...filters, limit: PAGE_SIZE, offset };

    const { data: result, isLoading } = useQuery({
        queryKey: ['treasury', 'transactions', queryFilters],
        queryFn: () => listTransactions(queryFilters),
    });

    const { data: accounts } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const { data: categories } = useQuery({ queryKey: ['treasury', 'categories'], queryFn: listCategories });

    const transferMutation = useMutation({
        mutationFn: transferFunds,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setIsTransferOpen(false);
        },
    });

    const createTxnMutation = useMutation({
        mutationFn: createTransaction,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setIsNewTxnOpen(false);
        },
    });

    const voidMutation = useMutation({
        mutationFn: ({ id, reason }: { id: number; reason: string }) => voidTransaction(id, reason),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setVoidingTxn(null);
        },
    });

    const handleFilterChange = (key: keyof TransactionParams, value: string) => {
        setOffset(0);
        setFilters(prev => ({ ...prev, [key]: value }));
    };

    const transactions = result?.results ?? [];
    const totalCount = result?.count ?? 0;
    const totalPages = Math.ceil(totalCount / PAGE_SIZE);
    const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

    const csvUrl = getTransactionsCsvUrl(filters);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center bg-white p-4 rounded-3xl border border-slate-200 shadow-sm">
                <div className="flex flex-wrap gap-2 w-full md:w-auto">
                    <input
                        type="date"
                        value={filters.date_from}
                        onChange={e => handleFilterChange('date_from', e.target.value)}
                        className="rounded-md border-slate-300 text-sm p-2 border"
                    />
                    <input
                        type="date"
                        value={filters.date_to}
                        onChange={e => handleFilterChange('date_to', e.target.value)}
                        className="rounded-md border-slate-300 text-sm p-2 border"
                    />
                    <select
                        value={filters.account}
                        onChange={e => handleFilterChange('account', e.target.value)}
                        className="rounded-md border-slate-300 text-sm p-2 border max-w-[150px]"
                    >
                        <option value="">Todas las cuentas</option>
                        {accounts?.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                    <select
                        value={filters.direction}
                        onChange={e => handleFilterChange('direction', e.target.value)}
                        className="rounded-md border-slate-300 text-sm p-2 border"
                    >
                        <option value="">Todos (In/Out)</option>
                        <option value="IN">Ingresos</option>
                        <option value="OUT">Egresos</option>
                        <option value="ADJUST">Ajustes</option>
                    </select>
                    <select
                        value={filters.category}
                        onChange={e => handleFilterChange('category', e.target.value)}
                        className="rounded-md border-slate-300 text-sm p-2 border max-w-[140px]"
                    >
                        <option value="">Todas las categorías</option>
                        {categories?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                </div>

                <div className="flex flex-wrap gap-2 w-full md:w-auto">
                    <div className="relative flex-1 md:w-56">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Buscar..."
                            value={filters.search}
                            onChange={e => handleFilterChange('search', e.target.value)}
                            className="pl-9 w-full rounded-full border-slate-300 text-sm p-2 border"
                        />
                    </div>
                    <a
                        href={csvUrl}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-full border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium"
                        download
                    >
                        <Download className="h-4 w-4" />
                        CSV
                    </a>
                    {canManage && (
                        <>
                            <Button onClick={() => setIsNewTxnOpen(true)} variant="outline" className="rounded-full">
                                <Plus className="mr-1.5 h-4 w-4" />
                                Nuevo
                            </Button>
                            <Button onClick={() => setIsTransferOpen(true)} variant="outline" className="rounded-full">
                                <ArrowLeftRight className="mr-1.5 h-4 w-4" />
                                Transferir
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {isLoading ? (
                <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
            ) : transactions.length === 0 ? (
                <EmptyState
                    title="No hay movimientos"
                    description="No se encontraron movimientos con los filtros seleccionados."
                />
            ) : (
                <>
                    <div className="space-y-3">
                        {transactions.map((t) => {
                            const transactionType = t.transaction_type || 'other';
                            const isIncome = t.direction === 'IN';
                            const isExpense = t.direction === 'OUT';
                            const isVoided = t.status === 'voided';

                            return (
                                <div key={t.id} className={cn(
                                    "bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all",
                                    isVoided && "opacity-50 border-slate-100"
                                )}>
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex gap-4 items-start flex-1">
                                            <div className={`p-2.5 rounded-xl ${
                                                isVoided ? 'bg-slate-100 text-slate-400' :
                                                transactionType === 'transfer' ? 'bg-blue-100 text-blue-600' :
                                                transactionType === 'expense' || transactionType === 'fixed_expense' ? 'bg-rose-100 text-rose-600' :
                                                transactionType === 'payroll' ? 'bg-purple-100 text-purple-600' :
                                                transactionType === 'sale' ? 'bg-emerald-100 text-emerald-600' :
                                                transactionType === 'reconciliation' ? 'bg-amber-100 text-amber-600' :
                                                        transactionType === 'stock_replenishment' ? 'bg-orange-100 text-orange-600' :
                                                        'bg-slate-100 text-slate-600'
                                                    }`}>
                                                        {transactionType === 'transfer' && <Repeat className="h-5 w-5" />}
                                                        {(transactionType === 'expense' || transactionType === 'fixed_expense') && <Receipt className="h-5 w-5" />}
                                                        {transactionType === 'payroll' && <Users className="h-5 w-5" />}
                                                        {transactionType === 'sale' && <FileText className="h-5 w-5" />}
                                                        {transactionType === 'reconciliation' && <RotateCcw className="h-5 w-5" />}
                                                        {transactionType === 'stock_replenishment' && <ShoppingCart className="h-5 w-5" />}
                                                    </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex flex-wrap items-center gap-2 mb-1">
                                                    <h3 className="text-sm font-semibold text-slate-900 truncate">{t.description}</h3>
                                                    {isVoided && (
                                                        <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-200 text-slate-500 whitespace-nowrap">
                                                            Anulado
                                                        </span>
                                                    )}
                                                    <span className={`px-2 py-0.5 text-xs font-medium rounded-full whitespace-nowrap ${
                                                        transactionType === 'transfer' ? 'bg-blue-100 text-blue-700' :
                                                        transactionType === 'expense' || transactionType === 'fixed_expense' ? 'bg-rose-100 text-rose-700' :
                                                        transactionType === 'payroll' ? 'bg-purple-100 text-purple-700' :
                                                        transactionType === 'sale' ? 'bg-emerald-100 text-emerald-700' :
                                                        transactionType === 'reconciliation' ? 'bg-amber-100 text-amber-700' :
                                                        transactionType === 'stock_replenishment' ? 'bg-orange-100 text-orange-700' :
                                                        'bg-slate-100 text-slate-700'
                                                    }`}>
                                                        {transactionType === 'transfer' ? `Transf. → ${t.related_account_name ?? ''}` :
                                                         transactionType === 'expense' ? 'Gasto' :
                                                         transactionType === 'fixed_expense' ? 'Gasto Fijo' :
                                                         transactionType === 'payroll' ? 'Sueldo' :
                                                         transactionType === 'sale' ? 'Venta' :
                                                         transactionType === 'reconciliation' ? 'Conciliación' :
                                                         transactionType === 'stock_replenishment' ? 'Reposición Stock' :
                                                         'Otro'}
                                                    </span>
                                                </div>

                                                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-500">
                                                    <span className="font-medium text-slate-700">{t.account_name}</span>
                                                    <span>{formatDateTimeAR(t.occurred_at)}</span>
                                                    {t.category_name && (
                                                        <span className="text-xs bg-slate-100 px-2 py-0.5 rounded-md">{t.category_name}</span>
                                                    )}
                                                </div>

                                                {t.reference_details && (
                                                    <div className="mt-2 text-xs text-slate-400">
                                                        {(transactionType === 'expense' || transactionType === 'fixed_expense') && t.reference_details.name && (
                                                            <span>📄 {t.reference_details.name}{t.reference_details.period ? ` (${t.reference_details.period})` : ''}</span>
                                                        )}
                                                        {transactionType === 'payroll' && t.reference_details.employee_name && (
                                                            <span>👤 {t.reference_details.employee_name}</span>
                                                        )}
                                                        {transactionType === 'stock_replenishment' && t.reference_id && (
                                                            <Link
                                                                href={`/app/gestion/stock/compras/${t.reference_id}`}
                                                                className="inline-flex items-center gap-1 text-orange-600 hover:text-orange-700 hover:underline font-medium"
                                                            >
                                                                <ShoppingCart className="h-3 w-3" />
                                                                Ver reposición
                                                                {t.reference_details.supplier_name ? ` — ${t.reference_details.supplier_name}` : ''}
                                                            </Link>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            <div className="text-right">
                                                <div className={`text-xl font-bold font-mono ${
                                                    isVoided ? 'text-slate-400 line-through' :
                                                    isIncome ? 'text-emerald-600' :
                                                    isExpense ? 'text-rose-600' :
                                                    'text-amber-600'
                                                }`}>
                                                    {isIncome ? '+' : isExpense ? '-' : '•'}
                                                    <Currency amount={t.amount} />
                                                </div>
                                            </div>
                                            {canManage && !isVoided && (
                                                <button
                                                    onClick={() => setVoidingTxn(t)}
                                                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                                    title="Anular"
                                                >
                                                    <Ban className="h-4 w-4" />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Pagination */}
                    {totalCount > PAGE_SIZE && (
                        <div className="flex items-center justify-between bg-white rounded-2xl border border-slate-200 p-4">
                            <span className="text-sm text-slate-500">
                                {offset + 1}–{Math.min(offset + PAGE_SIZE, totalCount)} de {totalCount} movimientos
                            </span>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={offset === 0}
                                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                    Anterior
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={offset + PAGE_SIZE >= totalCount}
                                    onClick={() => setOffset(offset + PAGE_SIZE)}
                                >
                                    Siguiente
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Void Modal */}
            {voidingTxn && (
                <VoidModal
                    isOpen={!!voidingTxn}
                    txn={voidingTxn}
                    onClose={() => setVoidingTxn(null)}
                    onSubmit={({ reason }) => voidMutation.mutate({ id: voidingTxn.id, reason })}
                    isLoading={voidMutation.isPending}
                />
            )}

            {/* New Transaction Modal */}
            {isNewTxnOpen && accounts && categories && (
                <NewTransactionModal
                    isOpen={isNewTxnOpen}
                    accounts={accounts}
                    categories={categories}
                    onClose={() => setIsNewTxnOpen(false)}
                    onSubmit={(data) => createTxnMutation.mutate(data)}
                    isLoading={createTxnMutation.isPending}
                />
            )}

            {/* Transfer Modal */}
            {isTransferOpen && accounts && (
                <TransferModal
                    isOpen={isTransferOpen}
                    accounts={accounts}
                    onClose={() => setIsTransferOpen(false)}
                    onSubmit={(data) => transferMutation.mutate(data)}
                    isLoading={transferMutation.isPending}
                />
            )}
        </div>
    );
}

function VoidModal({ isOpen, txn, onClose, onSubmit, isLoading }: any) {
    const [reason, setReason] = useState('');

    return (
        <Modal open={isOpen} onClose={onClose} title="Anular Transacción">
            <div className="space-y-4">
                <div className="flex items-start gap-3 p-4 bg-rose-50 border border-rose-200 rounded-xl">
                    <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-semibold text-rose-800">Esta acción no se puede deshacer fácilmente</p>
                        <p className="text-sm text-rose-700 mt-1">
                            La transacción <strong>{txn.description}</strong> de <strong>${parseFloat(txn.amount).toFixed(2)}</strong> será marcada como anulada y no contará en los saldos.
                        </p>
                        {txn.reference_type && ['expense', 'fixed_expense_period', 'payroll'].includes(txn.reference_type) && (
                            <p className="text-sm text-rose-700 mt-2">
                                El pago vinculado también se revertirá a estado pendiente.
                            </p>
                        )}
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Motivo de anulación (opcional)</label>
                    <input
                        type="text"
                        value={reason}
                        onChange={e => setReason(e.target.value)}
                        className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                        placeholder="Ej. Error de carga, duplicado..."
                    />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button
                        onClick={() => onSubmit({ reason })}
                        disabled={isLoading}
                        className="bg-rose-600 hover:bg-rose-700 text-white"
                    >
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Anular
                    </Button>
                </div>
            </div>
        </Modal>
    );
}

function NewTransactionModal({ isOpen, onClose, onSubmit, isLoading, accounts, categories }: any) {
    const [direction, setDirection] = useState<'IN' | 'OUT' | 'ADJUST'>('IN');
    const [account, setAccount] = useState('');
    const [amount, setAmount] = useState('');
    const [description, setDescription] = useState('');
    const [category, setCategory] = useState('');
    const [occurredAt, setOccurredAt] = useState(() => todayDateString());

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({
            account: Number(account),
            direction,
            amount: parseFloat(amount),
            occurred_at: occurredAt,
            description,
            category: category ? Number(category) : undefined,
        });
    };

    const directionCategories = categories.filter((c: any) =>
        direction === 'IN' ? c.direction === 'income' : c.direction === 'expense'
    );

    return (
        <Modal open={isOpen} onClose={onClose} title="Nuevo Movimiento Manual">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">Tipo</label>
                    <div className="flex gap-2">
                        {(['IN', 'OUT', 'ADJUST'] as const).map(d => (
                            <button
                                key={d}
                                type="button"
                                onClick={() => setDirection(d)}
                                className={cn(
                                    "flex-1 py-2 text-sm font-medium rounded-lg border-2 transition-all",
                                    direction === d
                                        ? d === 'IN' ? 'border-emerald-500 bg-emerald-50 text-emerald-700'
                                          : d === 'OUT' ? 'border-rose-500 bg-rose-50 text-rose-700'
                                          : 'border-amber-500 bg-amber-50 text-amber-700'
                                        : 'border-slate-200 text-slate-500 hover:border-slate-300'
                                )}
                            >
                                {d === 'IN' ? '+ Ingreso' : d === 'OUT' ? '- Egreso' : '≈ Ajuste'}
                            </button>
                        ))}
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Cuenta</label>
                    <select required value={account} onChange={e => setAccount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border">
                        <option value="">Seleccionar...</option>
                        {accounts.filter((a: any) => a.is_active).map((a: any) => (
                            <option key={a.id} value={a.id}>{a.name}</option>
                        ))}
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Monto</label>
                        <input required type="number" step="0.01" min="0.01" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border font-mono" placeholder="0.00" />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Fecha</label>
                        <input required type="date" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border" />
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Descripción</label>
                    <input type="text" value={description} onChange={e => setDescription(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border" placeholder="Ej. Pago proveedor, ingreso extra..." />
                </div>
                {direction !== 'ADJUST' && (
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Categoría (opcional)</label>
                        <select value={category} onChange={e => setCategory(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border">
                            <option value="">Sin categoría</option>
                            {directionCategories.map((c: any) => (
                                <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                        </select>
                    </div>
                )}
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Crear movimiento
                    </Button>
                </div>
            </form>
        </Modal>
    );
}

function TransferModal({ isOpen, onClose, onSubmit, isLoading, accounts }: any) {
    const [fromAccount, setFromAccount] = useState('');
    const [toAccount, setToAccount] = useState('');
    const [amount, setAmount] = useState('');
    const [description, setDescription] = useState('Transferencia interna');
    const [occurredAt, setOccurredAt] = useState(() => todayDateString());

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (fromAccount === toAccount) {
            alert("Las cuentas de origen y destino deben ser diferentes");
            return;
        }
        onSubmit({
            from_account: Number(fromAccount),
            to_account: Number(toAccount),
            amount,
            description,
            occurred_at: occurredAt
        });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title="Transferir Fondos">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Origen</label>
                        <select required value={fromAccount} onChange={e => setFromAccount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                            <option value="">Seleccionar...</option>
                            {accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Destino</label>
                        <select required value={toAccount} onChange={e => setToAccount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                            <option value="">Seleccionar...</option>
                            {accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Monto</label>
                    <input autoFocus required type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border font-mono text-lg" placeholder="0.00" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Fecha</label>
                    <input required type="date" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Notas</label>
                    <input type="text" value={description} onChange={e => setDescription(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Transferir</Button>
                </div>
            </form>
        </Modal>
    );
}
