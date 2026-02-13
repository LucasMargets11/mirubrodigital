"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, Calendar, Check, DollarSign } from 'lucide-react';
import { format, isPast, isToday } from 'date-fns';
import { es } from 'date-fns/locale';

import { listExpenses, listCategories, listAccounts, createExpense, payExpense, createCategory, Expense } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';
import { cn } from '@/lib/utils';

export function ExpensesClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [activeTab, setActiveTab] = useState<'pending' | 'paid'>('pending');
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [payingExpense, setPayingExpense] = useState<Expense | null>(null);

    const { data: expenses, isLoading } = useQuery({
        queryKey: ['treasury', 'expenses'],
        queryFn: listExpenses,
    });

    const { data: categories } = useQuery({ queryKey: ['treasury', 'categories'], queryFn: listCategories });
    const { data: accounts } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });

    const createMutation = useMutation({
        mutationFn: createExpense,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'expenses'] });
            setIsCreateOpen(false);
        },
    });

    const payMutation = useMutation({
        mutationFn: ({ id, account_id }: { id: number, account_id: number }) => payExpense(id, { account_id }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'expenses'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setPayingExpense(null);
        },
    });

    if (isLoading) return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;

    const filteredExpenses = expenses?.filter(e => activeTab === 'pending' ? e.status === 'pending' : e.status === 'paid') || [];

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-center bg-white p-4 rounded-3xl border border-slate-200 shadow-sm gap-4">
                <div className="flex p-1 bg-slate-100 rounded-lg">
                    <button
                        onClick={() => setActiveTab('pending')}
                        className={cn("px-4 py-2 text-sm font-medium rounded-md transition-all", activeTab === 'pending' ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900")}
                    >
                        Pendientes
                    </button>
                    <button
                        onClick={() => setActiveTab('paid')}
                        className={cn("px-4 py-2 text-sm font-medium rounded-md transition-all", activeTab === 'paid' ? "bg-white text-emerald-700 shadow-sm" : "text-slate-500 hover:text-slate-900")}
                    >
                        Pagados
                    </button>
                </div>

                {canManage && (
                    <Button onClick={() => setIsCreateOpen(true)} className="rounded-full w-full md:w-auto">
                        <Plus className="mr-2 h-4 w-4" />
                        Nuevo Gasto
                    </Button>
                )}
            </div>

            {filteredExpenses.length === 0 ? (
                <EmptyState
                    title={`No hay gastos ${activeTab === 'pending' ? 'pendientes' : 'pagados'}`}
                    description={activeTab === 'pending' ? "Registrá tus gastos recurrentes o únicos para no olvidarte de pagar nada." : "Acá vas a ver el historial de gastos que ya pagaste."}
                    actionLabel={activeTab === 'pending' && canManage ? "Crear gasto" : undefined}
                    onAction={() => setIsCreateOpen(true)}
                />
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredExpenses.map((expense) => (
                        <div key={expense.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden">
                            {/* Due Date Indicator */}
                            {activeTab === 'pending' && (
                                <div className={cn("absolute top-0 left-0 w-1 h-full",
                                    isPast(new Date(expense.due_date)) && !isToday(new Date(expense.due_date)) ? "bg-rose-500" :
                                        isToday(new Date(expense.due_date)) ? "bg-amber-500" : "bg-slate-300"
                                )} />
                            )}

                            <div className="pl-2">
                                <div className="flex justify-between items-start mb-2">
                                    <span className="text-xs text-slate-500 uppercase tracking-wider bg-slate-100 px-2 py-1 rounded-md">{expense.category_name || 'Sin cat.'}</span>
                                    <span className="text-lg font-bold font-mono text-slate-900"><Currency amount={expense.amount} /></span>
                                </div>
                                <h3 className="text-lg font-semibold text-slate-800 leading-tight mb-4">{expense.name}</h3>

                                <div className="flex items-center text-sm text-slate-500 mb-4">
                                    <Calendar className="h-4 w-4 mr-2" />
                                    {activeTab === 'pending' ? (
                                        <span className={cn(
                                            isPast(new Date(expense.due_date)) && !isToday(new Date(expense.due_date)) ? "text-rose-600 font-medium" :
                                                isToday(new Date(expense.due_date)) ? "text-amber-600 font-medium" : ""
                                        )}>
                                            Vence: {format(new Date(expense.due_date), 'dd/MM/yyyy')}
                                        </span>
                                    ) : (
                                        <span>Pagado el: {expense.paid_at ? format(new Date(expense.paid_at), 'dd/MM/yyyy') : '-'}</span>
                                    )}
                                </div>

                                {activeTab === 'pending' && canManage && (
                                    <Button onClick={() => setPayingExpense(expense)} className="w-full" variant="outline">
                                        <Check className="mr-2 h-4 w-4" />
                                        Registrar Pago
                                    </Button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {isCreateOpen && categories && (
                <ExpenseFormModal
                    isOpen={isCreateOpen}
                    categories={categories}
                    onClose={() => setIsCreateOpen(false)}
                    onSubmit={(data) => createMutation.mutate(data)}
                    isLoading={createMutation.isPending}
                />
            )}

            {payingExpense && accounts && (
                <PayExpenseModal
                    isOpen={!!payingExpense}
                    expense={payingExpense}
                    accounts={accounts}
                    onClose={() => setPayingExpense(null)}
                    onSubmit={(data) => payMutation.mutate({ ...data, id: payingExpense.id })}
                    isLoading={payMutation.isPending}
                />
            )}
        </div>
    );
}

function ExpenseFormModal({ isOpen, onClose, onSubmit, isLoading, categories }: any) {
    const queryClient = useQueryClient();
    const [name, setName] = useState('');
    const [amount, setAmount] = useState('');
    const [category, setCategory] = useState('');
    const [dueDate, setDueDate] = useState('');
    const [isCreatingCategory, setIsCreatingCategory] = useState(false);
    const [newCategoryName, setNewCategoryName] = useState('');

    const createCategoryMutation = useMutation({
        mutationFn: createCategory,
        onSuccess: (newCat) => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'categories'] });
            setCategory(newCat.id.toString());
            setIsCreatingCategory(false);
            setNewCategoryName('');
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({
            name,
            amount: parseFloat(amount),
            category: category ? Number(category) : null,
            due_date: dueDate
        });
    };

    const handleCreateCategory = () => {
        if (newCategoryName.trim()) {
            createCategoryMutation.mutate({ name: newCategoryName.trim(), direction: 'expense' });
        }
    };

    return (
        <Modal open={isOpen} onClose={onClose} title="Nuevo Gasto">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Descripción</label>
                    <input autoFocus required type="text" value={name} onChange={e => setName(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" placeholder="Ej. Internet, Alquiler..." />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Categoría</label>
                    {!isCreatingCategory ? (
                        <div className="flex gap-2">
                            <select value={category} onChange={e => setCategory(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                                <option value="">Seleccionar...</option>
                                {categories.filter((c: any) => c.direction === 'expense').map((c: any) => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                            <Button type="button" variant="outline" onClick={() => setIsCreatingCategory(true)} className="mt-1 whitespace-nowrap">
                                <Plus className="h-4 w-4" />
                            </Button>
                        </div>
                    ) : (
                        <div className="mt-1 flex gap-2">
                            <input
                                type="text"
                                value={newCategoryName}
                                onChange={e => setNewCategoryName(e.target.value)}
                                placeholder="Nueva categoría..."
                                className="block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
                            />
                            <Button type="button" onClick={handleCreateCategory} disabled={createCategoryMutation.isPending || !newCategoryName.trim()}>
                                {createCategoryMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                            </Button>
                            <Button type="button" variant="outline" onClick={() => { setIsCreatingCategory(false); setNewCategoryName(''); }}>
                                ✕
                            </Button>
                        </div>
                    )}
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Monto</label>
                    <input required type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Fecha de Vencimiento</label>
                    <input required type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Crear Gasto</Button>
                </div>
            </form>
        </Modal>
    );
}

function PayExpenseModal({ isOpen, onClose, onSubmit, isLoading, accounts, expense }: any) {
    const [accountId, setAccountId] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({ account_id: Number(accountId) });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title={`Pagar: ${expense.name}`}>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="p-4 bg-slate-50 rounded-md mb-4">
                    <p className="text-sm text-slate-500">Monto a pagar</p>
                    <p className="text-2xl font-bold text-slate-900"><Currency amount={expense.amount} /></p>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700">Pagar con cuenta</label>
                    <select required value={accountId} onChange={e => setAccountId(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                        <option value="">Seleccionar...</option>
                        {accounts.filter((a: any) => a.is_active).map((a: any) => (
                            <option key={a.id} value={a.id}>{a.name} ({a.type})</option>
                        ))}
                    </select>
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Confirmar Pago</Button>
                </div>
            </form>
        </Modal>
    );
}
