"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, User, DollarSign, Calendar } from 'lucide-react';
import { format } from 'date-fns';

import { listEmployees, createEmployee, listPayrollPayments, createPayrollPayment, listAccounts, Employee } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';

export function PayrollClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [isEmployeeModalOpen, setIsEmployeeModalOpen] = useState(false);
    const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);

    const { data: employees, isLoading: loadingEmployees } = useQuery({ queryKey: ['treasury', 'employees'], queryFn: listEmployees });
    const { data: payments, isLoading: loadingPayments } = useQuery({ queryKey: ['treasury', 'payroll-payments'], queryFn: listPayrollPayments });
    const { data: accounts } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });

    const createEmployeeMutation = useMutation({
        mutationFn: createEmployee,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'employees'] });
            setIsEmployeeModalOpen(false);
        },
    });

    const createPaymentMutation = useMutation({
        mutationFn: createPayrollPayment,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'payroll-payments'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] }); // Update account balance
            setIsPaymentModalOpen(false);
        },
    });

    if (loadingEmployees || loadingPayments) return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;

    return (
        <div className="space-y-8">
            {/* EMPLOYEES SECTION */}
            <section className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-lg font-semibold text-slate-900">Empleados</h2>
                    {canManage && (
                        <Button onClick={() => setIsEmployeeModalOpen(true)} size="sm" variant="outline">
                            <Plus className="mr-2 h-4 w-4" />
                            Nuevo Empleado
                        </Button>
                    )}
                </div>

                {!employees || employees.length === 0 ? (
                    <EmptyState
                        title="No hay empleados registrados"
                        description="Agregá a tus empleados para poder registrar los pagos de sueldos."
                        actionLabel={canManage ? "Agregar empleado" : undefined}
                        onAction={() => setIsEmployeeModalOpen(true)}
                        className="py-6"
                    />
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {employees.map(emp => (
                            <div key={emp.id} className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex items-center gap-3">
                                <div className="bg-indigo-100 p-2 rounded-full">
                                    <User className="h-5 w-5 text-indigo-700" />
                                </div>
                                <div>
                                    <h3 className="font-semibold text-slate-900">{emp.full_name}</h3>
                                    <p className="text-xs text-slate-500">Base: <Currency amount={emp.base_salary} /> / {emp.pay_frequency === 'monthly' ? 'mes' : 'sem'}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            {/* PAYMENTS SECTION */}
            <section className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-lg font-semibold text-slate-900">Historial de Pagos</h2>
                    {canManage && employees && employees.length > 0 && (
                        <Button onClick={() => setIsPaymentModalOpen(true)}>
                            <DollarSign className="mr-2 h-4 w-4" />
                            Registrar Pago
                        </Button>
                    )}
                </div>

                {!payments || payments.length === 0 ? (
                    <div className="text-center py-6 text-slate-500 text-sm italic border rounded-lg border-dashed">
                        No hay pagos registrados aún.
                    </div>
                ) : (
                    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
                        <table className="min-w-full divide-y divide-slate-200">
                            <thead className="bg-slate-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Fecha</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Empleado</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Cuenta</th>
                                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Monto</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-slate-200">
                                {payments.map((p) => (
                                    <tr key={p.id}>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                            {format(new Date(p.paid_at), 'dd/MM/yyyy')}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-medium">
                                            {p.employee_name}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                            {p.account_name}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-bold text-right">
                                            <Currency amount={p.amount} />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            {isEmployeeModalOpen && (
                <EmployeeFormModal
                    isOpen={isEmployeeModalOpen}
                    onClose={() => setIsEmployeeModalOpen(false)}
                    onSubmit={(data: any) => createEmployeeMutation.mutate(data)}
                    isLoading={createEmployeeMutation.isPending}
                />
            )}

            {isPaymentModalOpen && employees && accounts && (
                <PaymentFormModal
                    isOpen={isPaymentModalOpen}
                    employees={employees}
                    accounts={accounts}
                    onClose={() => setIsPaymentModalOpen(false)}
                    onSubmit={(data: any) => createPaymentMutation.mutate(data)}
                    isLoading={createPaymentMutation.isPending}
                />
            )}
        </div>
    );
}

function EmployeeFormModal({ isOpen, onClose, onSubmit, isLoading }: any) {
    const [fullName, setFullName] = useState('');
    const [baseSalary, setBaseSalary] = useState('');
    const [payFrequency, setPayFrequency] = useState('monthly');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({ full_name: fullName, base_salary: baseSalary, pay_frequency: payFrequency });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title="Nuevo Empleado">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Nombre Completo</label>
                    <input autoFocus required type="text" value={fullName} onChange={e => setFullName(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Salario Base</label>
                    <input required type="number" step="0.01" value={baseSalary} onChange={e => setBaseSalary(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Frecuencia</label>
                    <select value={payFrequency} onChange={e => setPayFrequency(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                        <option value="monthly">Mensual</option>
                        <option value="weekly">Semanal</option>
                    </select>
                </div>
                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Guardar</Button>
                </div>
            </form>
        </Modal>
    );
}

function PaymentFormModal({ isOpen, onClose, onSubmit, isLoading, employees, accounts }: any) {
    const [employeeId, setEmployeeId] = useState('');
    const [amount, setAmount] = useState('');
    const [accountId, setAccountId] = useState('');
    const [paidAt, setPaidAt] = useState(new Date().toISOString().split('T')[0]);

    const handleEmployeeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const id = e.target.value;
        setEmployeeId(id);
        const emp = employees.find((em: any) => em.id.toString() === id);
        if (emp) {
            setAmount(emp.base_salary);
        }
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({
            employee: Number(employeeId),
            amount,
            account: Number(accountId),
            paid_at: paidAt
        });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title="Registrar Pago Sueldo">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Empleado</label>
                    <select required value={employeeId} onChange={handleEmployeeChange} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                        <option value="">Seleccionar...</option>
                        {employees.map((e: any) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Monto</label>
                    <input required type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Cuenta de origen (Pago)</label>
                    <select required value={accountId} onChange={e => setAccountId(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border">
                        <option value="">Seleccionar...</option>
                        {accounts.filter((a: any) => a.is_active).map((a: any) => <option key={a.id} value={a.id}>{a.name} ({a.type})</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Fecha de Pago</label>
                    <input required type="date" value={paidAt} onChange={e => setPaidAt(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border" />
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Confirmar</Button>
                </div>
            </form>
        </Modal>
    );
}
