"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftRight, Loader2, Search, ArrowDownCircle, ArrowUpCircle, CheckCircle2, Receipt, Users, RotateCcw, FileText, TrendingDown, TrendingUp, Repeat } from 'lucide-react';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

import { listTransactions, listAccounts, listCategories, transferFunds, TransactionParams } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';

export function TransactionsClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [isTransferOpen, setIsTransferOpen] = useState(false);

    // Filters state
    const [filters, setFilters] = useState<TransactionParams>({
        search: '',
        account: '',
        category: '',
        direction: '',
        date_from: format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd'), // Start of month
        date_to: format(new Date(), 'yyyy-MM-dd'),
    });

    const { data: transactions, isLoading } = useQuery({
        queryKey: ['treasury', 'transactions', filters],
        queryFn: () => listTransactions(filters),
    });

    const { data: accounts } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const { data: categories } = useQuery({ queryKey: ['treasury', 'categories'], queryFn: listCategories });

    const transferMutation = useMutation({
        mutationFn: transferFunds,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] }); // Update balances
            setIsTransferOpen(false);
        },
    });

    const handleFilterChange = (key: keyof TransactionParams, value: string) => {
        setFilters(prev => ({ ...prev, [key]: value }));
    };

    if (isLoading) return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center bg-white p-4 rounded-3xl border border-slate-200 shadow-sm">
                <div className="flex flex-wrap gap-2 w-full md:w-auto">
                    {/* Filters */}
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
                </div>

                <div className="flex gap-2 w-full md:w-auto">
                    <div className="relative flex-1 md:w-64">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Buscar..."
                            value={filters.search}
                            onChange={e => handleFilterChange('search', e.target.value)}
                            className="pl-9 w-full rounded-full border-slate-300 text-sm p-2 border"
                        />
                    </div>
                    {canManage && (
                        <Button onClick={() => setIsTransferOpen(true)} variant="outline" className="rounded-full">
                            <ArrowLeftRight className="mr-2 h-4 w-4" />
                            Transferir
                        </Button>
                    )}
                </div>
            </div>

            {!transactions || transactions.length === 0 ? (
                <EmptyState
                    title="No hay movimientos"
                    description="No se encontraron movimientos con los filtros seleccionados."
                />
            ) : (
                <div className="space-y-3">
                    {transactions.map((t) => {
                        const transactionType = t.transaction_type || 'other';
                        const isIncome = t.direction === 'IN';
                        const isExpense = t.direction === 'OUT';

                        return (
                            <div key={t.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all">
                                <div className="flex items-start justify-between gap-4">
                                    {/* Left: Icon + Info */}
                                    <div className="flex gap-4 items-start flex-1">
                                        {/* Icon */}
                                        <div className={`p-2.5 rounded-xl ${transactionType === 'transfer' ? 'bg-blue-100 text-blue-600' :
                                                transactionType === 'expense' ? 'bg-rose-100 text-rose-600' :
                                                    transactionType === 'payroll' ? 'bg-purple-100 text-purple-600' :
                                                        transactionType === 'sale' ? 'bg-emerald-100 text-emerald-600' :
                                                            transactionType === 'reconciliation' ? 'bg-amber-100 text-amber-600' :
                                                                'bg-slate-100 text-slate-600'
                                            }`}>
                                            {transactionType === 'transfer' && <Repeat className="h-5 w-5" />}
                                            {transactionType === 'expense' && <Receipt className="h-5 w-5" />}
                                            {transactionType === 'payroll' && <Users className="h-5 w-5" />}
                                            {transactionType === 'sale' && <FileText className="h-5 w-5" />}
                                            {transactionType === 'reconciliation' && <RotateCcw className="h-5 w-5" />}
                                            {transactionType === 'other' && (isIncome ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />)}
                                        </div>

                                        {/* Info */}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-start gap-2 mb-1">
                                                <h3 className="font-semibold text-slate-900 text-base leading-tight">
                                                    {t.description}
                                                </h3>
                                                <span className={`px-2 py-0.5 text-xs font-medium rounded-full whitespace-nowrap ${transactionType === 'transfer' ? 'bg-blue-100 text-blue-700' :
                                                        transactionType === 'expense' ? 'bg-rose-100 text-rose-700' :
                                                            transactionType === 'payroll' ? 'bg-purple-100 text-purple-700' :
                                                                transactionType === 'sale' ? 'bg-emerald-100 text-emerald-700' :
                                                                    transactionType === 'reconciliation' ? 'bg-amber-100 text-amber-700' :
                                                                        'bg-slate-100 text-slate-700'
                                                    }`}>
                                                    {transactionType === 'transfer' ? 'Transferencia' :
                                                        transactionType === 'expense' ? 'Gasto' :
                                                            transactionType === 'payroll' ? 'Sueldo' :
                                                                transactionType === 'sale' ? 'Venta' :
                                                                    transactionType === 'reconciliation' ? 'Conciliación' :
                                                                        'Otro'}
                                                </span>
                                            </div>

                                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-500">
                                                <span className="font-medium text-slate-700">{t.account_name}</span>
                                                <span>{format(new Date(t.occurred_at), 'dd/MM/yyyy HH:mm')}</span>
                                                {t.category_name && (
                                                    <span className="text-xs bg-slate-100 px-2 py-0.5 rounded-md">{t.category_name}</span>
                                                )}
                                            </div>

                                            {/* Reference Details */}
                                            {t.reference_details && (
                                                <div className="mt-2 text-xs text-slate-400">
                                                    {transactionType === 'expense' && t.reference_details.name && (
                                                        <span>📄 {t.reference_details.name}</span>
                                                    )}
                                                    {transactionType === 'payroll' && t.reference_details.employee_name && (
                                                        <span>👤 {t.reference_details.employee_name}</span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Right: Amount */}
                                    <div className="text-right">
                                        <div className={`text-xl font-bold font-mono ${isIncome ? 'text-emerald-600' :
                                                isExpense ? 'text-rose-600' :
                                                    'text-amber-600'
                                            }`}>
                                            {isIncome ? '+' : isExpense ? '-' : '•'}
                                            <Currency amount={t.amount} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

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

function TransferModal({ isOpen, onClose, onSubmit, isLoading, accounts }: any) {
    const [fromAccount, setFromAccount] = useState('');
    const [toAccount, setToAccount] = useState('');
    const [amount, setAmount] = useState('');
    const [description, setDescription] = useState('Transferencia interna');
    const [occurredAt, setOccurredAt] = useState(new Date().toISOString().split('T')[0]);

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
