"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, User, DollarSign, Calendar, Pencil, PowerOff, RotateCcw, AlertTriangle } from 'lucide-react';
import { todayDateString, formatDateFromTimestampAR } from '@/lib/dates';

import { listEmployees, createEmployee, updateEmployee, listPayrollPayments, createPayrollPayment, revertPayrollPayment, listAccounts, Employee, PayrollPayment } from '@/lib/api/treasury';
import { cn } from '@/lib/utils';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '../components/empty-state';

export function PayrollClient({ canManage }: { canManage: boolean }) {
    const queryClient = useQueryClient();
    const [isEmployeeModalOpen, setIsEmployeeModalOpen] = useState(false);
    const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
    const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
    const [revertingPayment, setRevertingPayment] = useState<PayrollPayment | null>(null);

    const { data: employees, isLoading: loadingEmployees } = useQuery({ queryKey: ['treasury', 'employees'], queryFn: listEmployees });
    const { data: paymentsResult, isLoading: loadingPayments } = useQuery({ queryKey: ['treasury', 'payroll-payments'], queryFn: () => listPayrollPayments({ limit: 100 }) });
    const { data: accounts } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });

    const payments = paymentsResult?.results ?? [];

    const createEmployeeMutation = useMutation({
        mutationFn: createEmployee,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'employees'] });
            setIsEmployeeModalOpen(false);
        },
    });

    const updateEmployeeMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: Partial<Employee> }) => updateEmployee(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'employees'] });
            setEditingEmployee(null);
        },
    });

    const createPaymentMutation = useMutation({
        mutationFn: createPayrollPayment,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'payroll-payments'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setIsPaymentModalOpen(false);
        },
    });

    const revertPaymentMutation = useMutation({
        mutationFn: ({ id, reason }: { id: number; reason: string }) => revertPayrollPayment(id, reason),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['treasury', 'payroll-payments'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'transactions'] });
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts'] });
            setRevertingPayment(null);
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
                            <div key={emp.id} className={cn("bg-white rounded-xl border border-slate-200 p-4 shadow-sm", !emp.is_active && "opacity-60")}>
                                <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                        <div className={cn("p-2 rounded-full", emp.is_active ? 'bg-indigo-100' : 'bg-slate-100')}>
                                            <User className={cn("h-5 w-5", emp.is_active ? 'text-indigo-700' : 'text-slate-400')} />
                                        </div>
                                        <div className="min-w-0">
                                            <h3 className="font-semibold text-slate-900 truncate">{emp.full_name}</h3>
                                            <p className="text-xs text-slate-500">Base: <Currency amount={emp.base_salary} /> / {emp.pay_frequency === 'monthly' ? 'mes' : 'sem'}</p>
                                            {!emp.is_active && <span className="text-xs text-rose-500 font-medium">Inactivo</span>}
                                        </div>
                                    </div>
                                    {canManage && (
                                        <div className="flex gap-1 shrink-0">
                                            <button onClick={() => setEditingEmployee(emp)} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg" title="Editar">
                                                <Pencil className="h-4 w-4" />
                                            </button>
                                            {emp.is_active && (
                                                <button
                                                    onClick={() => updateEmployeeMutation.mutate({ id: emp.id, data: { is_active: false } })}
                                                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg"
                                                    title="Desactivar"
                                                >
                                                    <PowerOff className="h-4 w-4" />
                                                </button>
                                            )}
                                        </div>
                                    )}
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

                {payments.length === 0 ? (
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
                                    {canManage && <th className="px-6 py-3" />}
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-slate-200">
                                {payments.map((p) => (
                                    <tr key={p.id} className={cn(p.status === 'reverted' && 'opacity-50')}>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                            {formatDateFromTimestampAR(p.paid_at)}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-medium">
                                            {p.employee_name}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                            {p.account_name}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-bold text-right">
                                            {p.status === 'reverted'
                                                ? <span className="line-through text-slate-400"><Currency amount={p.amount} /></span>
                                                : <Currency amount={p.amount} />
                                            }
                                        </td>
                                        {canManage && (
                                            <td className="px-4 py-4">
                                                {p.status !== 'reverted' && (
                                                    <button
                                                        onClick={() => setRevertingPayment(p)}
                                                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg"
                                                        title="Revertir pago"
                                                    >
                                                        <RotateCcw className="h-4 w-4" />
                                                    </button>
                                                )}
                                            </td>
                                        )}
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

            {editingEmployee && (
                <EmployeeEditModal
                    isOpen={!!editingEmployee}
                    employee={editingEmployee}
                    onClose={() => setEditingEmployee(null)}
                    onSubmit={(data: any) => updateEmployeeMutation.mutate({ id: editingEmployee.id, data })}
                    isLoading={updateEmployeeMutation.isPending}
                />
            )}

            {revertingPayment && (
                <RevertPaymentModal
                    isOpen={!!revertingPayment}
                    payment={revertingPayment}
                    onClose={() => setRevertingPayment(null)}
                    onSubmit={({ reason }: { reason: string }) => revertPaymentMutation.mutate({ id: revertingPayment.id, reason })}
                    isLoading={revertPaymentMutation.isPending}
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

function EmployeeEditModal({ isOpen, employee, onClose, onSubmit, isLoading }: any) {
    const [fullName, setFullName] = useState(employee.full_name);
    const [baseSalary, setBaseSalary] = useState(employee.base_salary);
    const [payFrequency, setPayFrequency] = useState(employee.pay_frequency);
    const [isActive, setIsActive] = useState(employee.is_active);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit({ full_name: fullName, base_salary: baseSalary, pay_frequency: payFrequency, is_active: isActive });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title={`Editar: ${employee.full_name}`}>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700">Nombre Completo</label>
                    <input required type="text" value={fullName} onChange={e => setFullName(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm sm:text-sm p-2 border" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Salario Base</label>
                        <input required type="number" step="0.01" value={baseSalary} onChange={e => setBaseSalary(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm sm:text-sm p-2 border" />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700">Frecuencia</label>
                        <select value={payFrequency} onChange={e => setPayFrequency(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm sm:text-sm p-2 border">
                            <option value="monthly">Mensual</option>
                            <option value="weekly">Semanal</option>
                        </select>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <input type="checkbox" id="is_active" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="rounded border-slate-300" />
                    <label htmlFor="is_active" className="text-sm font-medium text-slate-700">Empleado activo</label>
                </div>
                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={isLoading}>{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Guardar cambios</Button>
                </div>
            </form>
        </Modal>
    );
}

function RevertPaymentModal({ isOpen, payment, onClose, onSubmit, isLoading }: any) {
    const [reason, setReason] = useState('');
    return (
        <Modal open={isOpen} onClose={onClose} title="Revertir Pago de Sueldo">
            <div className="space-y-4">
                <div className="flex items-start gap-3 p-4 bg-rose-50 border border-rose-200 rounded-xl">
                    <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-semibold text-rose-800">¿Revertir el pago a {payment.employee_name}?</p>
                        <p className="text-sm text-rose-700 mt-1">El monto <strong>${parseFloat(payment.amount).toFixed(2)}</strong> será reintegrado a la cuenta y la transacción quedará anulada.</p>
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700">Motivo (opcional)</label>
                    <input type="text" value={reason} onChange={e => setReason(e.target.value)} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm sm:text-sm p-2 border" placeholder="Ej. Error de monto, pago duplicado..." />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button onClick={() => onSubmit({ reason })} disabled={isLoading} className="bg-rose-600 hover:bg-rose-700 text-white">
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Revertir pago
                    </Button>
                </div>
            </div>
        </Modal>
    );
}

function PaymentFormModal({ isOpen, onClose, onSubmit, isLoading, employees, accounts }: any) {
    const [employeeId, setEmployeeId] = useState('');
    const [amount, setAmount] = useState('');
    const [accountId, setAccountId] = useState('');
    const [paidAt, setPaidAt] = useState(() => todayDateString());

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
