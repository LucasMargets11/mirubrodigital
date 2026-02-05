"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Loader2, Edit, AlertCircle, RefreshCw } from 'lucide-react';

import { Account, listAccounts, createAccount, updateAccount, reconcileAccount } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';

export function AccountsClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingAccount, setEditingAccount] = useState<Account | null>(null);
    const [reconcilingAccount, setReconcilingAccount] = useState<Account | null>(null);

    const { data: accounts, isLoading } = useQuery({
        queryKey: ['treasury', 'accounts'],
        queryFn: listAccounts,
    });

    const createMutation = useMutation({
        mutationFn: createAccount,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setIsCreateOpen(false);
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: any) => updateAccount(data.id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setEditingAccount(null);
        },
    });
    
    const reconcileMutation = useMutation({
        mutationFn: ({ id, real_balance, occurred_at }: { id: number, real_balance: string, occurred_at: string }) => 
            reconcileAccount(id, real_balance, occurred_at),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setReconcilingAccount(null);
        }
    });

    if (isLoading) {
        return (
            <div className="flex justify-center p-12">
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
        );
    }

    if (!accounts || accounts.length === 0) {
        return (
            <>
                <EmptyState
                    title="No tenés cuentas registradas"
                    description="Creá tus cuentas de Caja, Banco, MercadoPago, etc. para empezar a registrar movimientos."
                    actionLabel={canManage ? "Crear primera cuenta" : undefined}
                    onAction={() => setIsCreateOpen(true)}
                />
                {isCreateOpen && (
                    <AccountFormModal
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
            <div className="flex justify-between items-center bg-white p-4 rounded-3xl border border-slate-200 shadow-sm">
                <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-slate-900">Cuentas</h2>
                    <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded-full">
                        {accounts.length}
                    </span>
                </div>
                {canManage && (
                    <Button onClick={() => setIsCreateOpen(true)} className="rounded-full">
                        <Plus className="mr-2 h-4 w-4" />
                        Nueva Cuenta
                    </Button>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {accounts.map((account) => (
                    <div key={account.id} className="bg-white rounded-3xl border border-slate-200 p-6 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow">
                        <div>
                             <div className="flex justify-between items-start mb-2">
                                <span className={`text-xs font-semibold px-2 py-1 rounded-full ${account.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>
                                    {account.is_active ? 'Activa' : 'Inactiva'}
                                </span>
                                <span className="text-xs text-slate-400 uppercase tracking-wider">{account.type}</span>
                            </div>
                            <h3 className="text-xl font-bold text-slate-900 mb-1">{account.name}</h3>
                            <div className="text-2xl font-mono text-slate-800">
                                <Currency amount={account.balance} />
                            </div>
                            <p className="text-xs text-slate-500 mt-2">Saldo contable (Inicial: <Currency amount={account.opening_balance} />)</p>
                        </div>

                        {canManage && (
                        <div className="mt-6 flex justify-between items-center border-t border-slate-100 pt-4">
                             <Button variant="ghost" size="sm" onClick={() => setReconcilingAccount(account)} className="text-blue-600 hover:text-blue-700 hover:bg-blue-50/50">
                                <RefreshCw className="h-4 w-4 mr-1.5" />
                                Conciliar
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setEditingAccount(account)} className="text-slate-500 hover:text-slate-700">
                                <Edit className="h-4 w-4" />
                            </Button>
                        </div>
                        )}
                    </div>
                ))}
            </div>

            {isCreateOpen && (
                <AccountFormModal
                    isOpen={isCreateOpen}
                    onClose={() => setIsCreateOpen(false)}
                    onSubmit={(data) => createMutation.mutate(data)}
                    isLoading={createMutation.isPending}
                />
            )}

            {editingAccount && (
                <AccountFormModal
                    isOpen={!!editingAccount}
                    account={editingAccount}
                    onClose={() => setEditingAccount(null)}
                    onSubmit={(data) => updateMutation.mutate({ ...data, id: editingAccount.id })}
                    isLoading={updateMutation.isPending}
                />
            )}
            
            {reconcilingAccount && (
                <ReconcileModal
                    isOpen={!!reconcilingAccount}
                    account={reconcilingAccount}
                    onClose={() => setReconcilingAccount(null)}
                    onSubmit={(data) => reconcileMutation.mutate({ ...data, id: reconcilingAccount.id })}
                    isLoading={reconcileMutation.isPending}
                />
            )}
        </div>
    );
}

function AccountFormModal({ isOpen, onClose, onSubmit, isLoading, account }: any) {
    const [name, setName] = useState(account?.name || '');
    const [type, setType] = useState(account?.type || 'cash');
    const [openingBalance, setOpeningBalance] = useState(account?.opening_balance || '0');
    
    // Only allow editing opening balance if creating (simplification, real world might differ)
    // or allow editing but warn it affects history. Let's allow simple edit.

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({ name, type, opening_balance: openingBalance });
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={account ? "Editar Cuenta" : "Nueva Cuenta"}>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Nombre</label>
                    <input autoFocus required type="text" value={name} onChange={e => setName(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Tipo</label>
                    <select value={type} onChange={e => setType(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                        <option value="cash">Efectivo / Caja</option>
                        <option value="bank">Banco</option>
                        <option value="mercadopago">MercadoPago / Wallet</option>
                        <option value="card_float">Tarjeta (Flotante)</option>
                        <option value="other">Otro</option>
                    </select>
                </div>
                 <div>
                    <label className="block text-sm font-medium text-slate-700">Saldo Inicial</label>
                    <input required type="number" step="0.01" value={openingBalance} onChange={e => setOpeningBalance(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                    <p className="text-xs text-slate-500 mt-1">Saldo al momento de creación.</p>
                </div>
                
                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Guardar</Button>
                </div>
            </form>
        </Modal>
    );
}

function ReconcileModal({ isOpen, onClose, onSubmit, isLoading, account }: any) {
    const [realBalance, setRealBalance] = useState('');
    const [occurredAt, setOccurredAt] = useState(new Date().toISOString().split('T')[0]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({ real_balance: realBalance, occurred_at: occurredAt });
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Conciliar Cuenta">
             <form onSubmit={handleSubmit} className="space-y-4">
                <div className="bg-blue-50 p-3 rounded-md flex items-start text-blue-800 text-sm">
                    <AlertCircle className="h-5 w-5 mr-2 shrink-0" />
                    <p>Ingresá el saldo real que ves en tu banco o caja. Se creará automáticamente un movimiento (Ajuste) por la diferencia.</p>
                </div>
                
                <div>
                    <label className="block text-sm font-medium text-slate-700">Saldo Real Actual</label>
                    <input autoFocus required type="number" step="0.01" value={realBalance} onChange={e => setRealBalance(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                 <div>
                    <label className="block text-sm font-medium text-slate-700">Fecha de corte</label>
                    <input required type="date" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                
                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Conciliar</Button>
                </div>
            </form>
        </Modal>
    );
}
