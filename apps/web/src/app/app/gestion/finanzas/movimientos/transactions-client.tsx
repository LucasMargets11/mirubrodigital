"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftRight, Loader2, Search, ArrowDownCircle, ArrowUpCircle, CheckCircle2 } from 'lucide-react';
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
                <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden shadow-sm">
                    <table className="min-w-full divide-y divide-slate-200">
                        <thead className="bg-slate-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Fecha</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Cuenta</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Descripción</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Categoría</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Monto</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-slate-200">
                            {transactions.map((t) => (
                                <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                        {format(new Date(t.occurred_at), 'dd/MM/yyyy HH:mm')}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-medium">
                                        {t.account_name}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-slate-700">
                                        <div className="flex flex-col">
                                            <span>{t.description}</span>
                                            {t.reference_type && (
                                                <span className="text-xs text-slate-400 capitalize">Ref: {t.reference_type} #{t.reference_id?.slice(0,8)}</span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                        {t.category_name || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-mono font-medium">
                                        <div className={`flex items-center justify-end gap-1 ${
                                            t.direction === 'IN' ? 'text-emerald-600' : 
                                            t.direction === 'OUT' ? 'text-rose-600' : 'text-amber-600'
                                        }`}>
                                            {t.direction === 'IN' ? '+' : t.direction === 'OUT' ? '-' : '•'}
                                            <Currency amount={t.amount} />
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
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
        <Modal isOpen={isOpen} onClose={onClose} title="Transferir Fondos">
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
