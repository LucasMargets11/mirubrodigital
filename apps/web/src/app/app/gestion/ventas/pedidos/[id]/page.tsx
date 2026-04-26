"use client";

import { useRouter } from 'next/navigation';
import { use, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { 
    useOrder, 
    useConfirmOrder, 
    useCancelOrder,
    useMarkOrderPreparation,
    useMarkOrderReady,
    useDeliverOrder,
    useRegisterOrderPayment 
} from '@/features/gestion/hooks';

import type { Order } from '@/features/gestion/types';

export default function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const router = useRouter();
    const { id: orderId } = use(params);
    
    const { data: order, isLoading, error } = useOrder(orderId);
    
    const confirmOrder = useConfirmOrder();
    const cancelOrder = useCancelOrder();
    const markInPrep = useMarkOrderPreparation();
    const markReady = useMarkOrderReady();
    const deliverOrder = useDeliverOrder();
    const registerPayment = useRegisterOrderPayment();

    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const [paymentAmount, setPaymentAmount] = useState('');
    const [paymentMethod, setPaymentMethod] = useState('cash');

    if (isLoading) return <div className="p-8 text-center">Cargando pedido...</div>;
    if (error || !order) return <div className="p-8 text-center text-red-500">Error al cargar pedido</div>;

    const orderData = order as any;

    const handleAction = async (action: 'confirm' | 'cancel' | 'prepare' | 'ready' | 'deliver', label: string) => {
        if (!confirm(`¿Confirmar acción: ${label}?`)) return;
        
        try {
            switch(action) {
                case 'confirm': await confirmOrder.mutateAsync(orderId); break;
                case 'cancel': await cancelOrder.mutateAsync(orderId); break;
                case 'prepare': await markInPrep.mutateAsync(orderId); break;
                case 'ready': await markReady.mutateAsync(orderId); break;
                case 'deliver': await deliverOrder.mutateAsync(orderId); break;
            }
        } catch (err: any) {
            alert(`Error: ${err?.message || 'Desconocido'}`);
        }
    };

    const handlePayment = async () => {
        if (!paymentAmount) return;
        try {
            await registerPayment.mutateAsync({
                id: orderId,
                payload: {
                    amount: Number(paymentAmount),
                    payment_method: paymentMethod,
                    notes: 'Pago registrado desde dashboard'
                }
            });
            setShowPaymentModal(false);
            setPaymentAmount('');
        } catch (err: any) {
            alert(`Error al registrar pago: ${err?.message}`);
        }
    };

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            draft: 'bg-gray-100 text-gray-800',
            pending_confirmation: 'bg-yellow-50 text-yellow-600',
            confirmed: 'bg-yellow-100 text-yellow-800',
            in_preparation: 'bg-blue-100 text-blue-800',
            ready_for_delivery: 'bg-purple-100 text-purple-800',
            delivered: 'bg-green-100 text-green-800',
            cancelled: 'bg-red-100 text-red-800',
        };
        return colors[status] || 'bg-gray-100';
    };

    return (
        <div className="p-6 max-w-5xl mx-auto space-y-6">
            <div className="flex justify-between items-start">
                <div>
                    <div className="flex items-center gap-3">
                        <h1 className="text-2xl font-bold text-slate-900">Pedido #{orderData.number}</h1>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium uppercase ${getStatusColor(orderData.status)}`}>
                            {orderData.status.replace(/_/g, ' ')}
                        </span>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium uppercase ${orderData.payment_status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-orange-100 text-orange-800'}`}>
                            {orderData.payment_status === 'paid' ? 'Pagado' : 'Pendiente Pago'}
                        </span>
                    </div>
                    <p className="text-slate-500 mt-1">Cliente: {orderData.customer_name || 'Consumidor Final'}</p>
                    <p className="text-slate-400 text-sm">{new Date(orderData.created_at).toLocaleString()}</p>
                </div>
                <button onClick={() => router.back()} className="text-slate-500 hover:text-slate-700">Volver</button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    {/* Items */}
                    <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
                        <div className="px-4 py-3 bg-slate-50 border-b font-medium">Items del Pedido</div>
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-slate-500 text-left">
                                <tr>
                                    <th className="px-4 py-2">Producto</th>
                                    <th className="px-4 py-2 text-center">Cant.</th>
                                    <th className="px-4 py-2 text-right">Unitario</th>
                                    <th className="px-4 py-2 text-right">Total</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y">
                                {orderData.items.map((item: any) => (
                                    <tr key={item.id}>
                                        <td className="px-4 py-3">{item.product_name || item.name_snapshot}</td>
                                        <td className="px-4 py-3 text-center">{item.quantity}</td>
                                        <td className="px-4 py-3 text-right">${Number(item.unit_price).toFixed(2)}</td>
                                        <td className="px-4 py-3 text-right font-medium">${Number(item.subtotal || item.total_price || (item.quantity * item.unit_price)).toFixed(2)}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot className="bg-slate-50 font-bold text-slate-800">
                                <tr>
                                    <td colSpan={3} className="px-4 py-3 text-right">Total:</td>
                                    <td className="px-4 py-3 text-right">${Number(orderData.total || (order as any).total_amount).toFixed(2)}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    {/* Payments */}
                    <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
                        <div className="flex justify-between items-center px-4 py-3 bg-slate-50 border-b">
                            <span className="font-medium">Pagos</span>
                            {orderData.payment_status !== 'paid' && orderData.status !== 'cancelled' && (
                                <button 
                                    onClick={() => setShowPaymentModal(true)}
                                    className="text-xs bg-green-600 text-white px-2 py-1 rounded hover:bg-green-700"
                                >
                                    registrar pago
                                </button>
                            )}
                        </div>
                        {orderData.payments.length === 0 ? (
                             <div className="p-4 text-slate-400 text-center text-sm">No hay pagos registrados.</div>
                        ) : (
                            <table className="w-full text-sm">
                                <thead className="bg-slate-50 text-slate-500 text-left">
                                    <tr>
                                        <th className="px-4 py-2">Fecha</th>
                                        <th className="px-4 py-2">Método</th>
                                        <th className="px-4 py-2 text-right">Monto</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {orderData.payments.map((p: any) => (
                                        <tr key={p.id}>
                                            <td className="px-4 py-2">{new Date(p.created_at).toLocaleDateString()}</td>
                                            <td className="px-4 py-2 capitalize">{p.payment_method}</td>
                                            <td className="px-4 py-2 text-right text-green-700 font-medium">${Number(p.amount).toFixed(2)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>

                <div className="space-y-6">
                    {/* Actions Panel */}
                    <div className="bg-white rounded-lg border shadow-sm p-4 sticky top-6">
                        <h3 className="font-medium text-slate-800 mb-4">Acciones</h3>
                        <div className="space-y-2 flex flex-col">
                            {(orderData.status === 'draft' || orderData.status === 'pending_confirmation') && (
                                <button 
                                    onClick={() => handleAction('confirm', 'Confirmar Pedido')}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-md font-medium transition-colors"
                                >
                                    Confirmar Pedido
                                </button>
                            )}

                            {orderData.status === 'confirmed' && (
                                <button 
                                    onClick={() => handleAction('prepare', 'Marcar en Preparación')}
                                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2 rounded-md font-medium transition-colors"
                                >
                                    Iniciar Preparación
                                </button>
                            )}

                            {orderData.status === 'in_preparation' && (
                                <button 
                                    onClick={() => handleAction('ready', 'Marcar Listo para Retirar')}
                                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-2 rounded-md font-medium transition-colors"
                                >
                                    Listo para entrega
                                </button>
                            )}

                            {(orderData.status === 'ready_for_delivery' || orderData.status === 'confirmed') && (
                                <button 
                                    onClick={() => handleAction('deliver', 'Entregar Pedido')}
                                    className="w-full bg-green-600 hover:bg-green-700 text-white py-2 rounded-md font-medium transition-colors"
                                >
                                    Entregar y Finalizar
                                </button>
                            )}

                            {orderData.status !== 'cancelled' && orderData.status !== 'delivered' && (
                                <button 
                                    onClick={() => handleAction('cancel', 'Cancelar Pedido')}
                                    className="w-full border border-red-200 text-red-600 hover:bg-red-50 py-2 rounded-md font-medium transition-colors mt-4"
                                >
                                    Cancelar Pedido
                                </button>
                            )}
                        </div>

                        
                        {/* Summary */}
                        <div className="mt-6 pt-4 border-t space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-slate-500">Subtotal</span>
                                <span>${Number(orderData.subtotal).toFixed(2)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-500">Impuestos</span>
                                <span>${Number(orderData.tax_amount).toFixed(2)}</span>
                            </div>
                            <div className="flex justify-between font-bold text-lg pt-2 border-t">
                                <span>Total</span>
                                <span>${Number(orderData.total_amount).toFixed(2)}</span>
                            </div>
                             <div className="flex justify-between text-green-700 pt-2">
                                <span>Pagado</span>
                                <span>${orderData.payments.reduce((acc: number, p: any) => acc + Number(p.amount), 0).toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Payment Modal */}
            {showPaymentModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-lg shadow-xl max-w-sm w-full p-6 space-y-4">
                        <h3 className="font-bold text-lg">Registrar Pago</h3>
                        
                        <div>
                            <label className="block text-sm font-medium mb-1">Monto</label>
                            <input 
                                type="number" 
                                className="w-full border rounded p-2"
                                value={paymentAmount}
                                onChange={e => setPaymentAmount(e.target.value)}
                                placeholder={`Restante: $${(Number(orderData.total_amount) - orderData.payments.reduce((acc: number, p: any) => acc + Number(p.amount), 0)).toFixed(2)}`}
                            />
                        </div>
                        
                        <div>
                            <label className="block text-sm font-medium mb-1">Método</label>
                            <select 
                                className="w-full border rounded p-2"
                                value={paymentMethod}
                                onChange={e => setPaymentMethod(e.target.value)}
                            >
                                <option value="cash">Efectivo</option>
                                <option value="credit_card">Tarjeta Crédito</option>
                                <option value="debit_card">Tarjeta Débito</option>
                                <option value="transfer">Transferencia</option>
                            </select>
                        </div>

                        <div className="flex justify-end gap-2 pt-2">
                            <button 
                                onClick={() => setShowPaymentModal(false)}
                                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded"
                            >
                                Cancelar
                            </button>
                            <button 
                                onClick={handlePayment}
                                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                                disabled={!paymentAmount}
                            >
                                Registrar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
