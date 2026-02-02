'use client';

import { useMemo } from 'react';

import type { KitchenItem, KitchenOrder, KitchenStatus } from '@/features/orders/types';
import { cn } from '@/lib/utils';

import { KitchenTicket } from './kitchen-ticket';

interface KitchenBoardProps {
    orders: KitchenOrder[];
    onUpdateItem: (itemId: string, status: KitchenStatus) => void;
    onUpdateOrder: (orderId: string, status: KitchenStatus) => void;
}

type ColumnId = 'pending' | 'in_progress' | 'ready';

const COLUMNS: { id: ColumnId; label: string; color: string }[] = [
    { id: 'pending', label: 'Pendiente', color: 'bg-orange-50 border-orange-200 text-orange-700' },
    { id: 'in_progress', label: 'En preparación', color: 'bg-blue-50 border-blue-200 text-blue-700' },
    { id: 'ready', label: 'Listo', color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
];

export function KitchenBoard({ orders, onUpdateItem, onUpdateOrder }: KitchenBoardProps) {
    const columns = useMemo(() => {
        const cols: Record<ColumnId, KitchenOrder[]> = {
            pending: [],
            in_progress: [],
            ready: [],
        };

        orders.forEach((order) => {
            const itemStatuses = order.items.map((i) => i.kitchen_status);
            
            let status: ColumnId = 'ready'; // Default if all ready/done

            if (itemStatuses.some((s) => s === 'pending')) {
                status = 'pending';
            } else if (itemStatuses.some((s) => s === 'in_progress')) {
                status = 'in_progress';
            }
            // else ready (or done, which stays in ready column until disappears)
            
            // If all done, we still show in ready? or filter out?
            // If API returns it, show in ready.
            
            cols[status].push(order);
        });

        return cols;
    }, [orders]);

    return (
        <div className="grid h-full grid-cols-1 gap-4 overflow-hidden lg:grid-cols-3">
            {COLUMNS.map((col) => (
                <div key={col.id} className="flex h-full flex-col overflow-hidden rounded-xl bg-slate-50/50 box-border border border-slate-200">
                    <div className={cn("flex items-center justify-between border-b px-4 py-3 font-semibold", col.color)}>
                        <span>{col.label}</span>
                        <span className="rounded-full bg-white/50 px-2 py-0.5 text-xs">
                            {columns[col.id].length}
                        </span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-3">
                        <div className="flex flex-col gap-3">
                            {columns[col.id].map((order) => (
                               <div key={order.id} className="h-auto">
                                    <KitchenTicket 
                                        order={order} 
                                        onUpdateItem={onUpdateItem} 
                                        onUpdateOrder={onUpdateOrder} 
                                    />
                               </div>
                            ))}
                            {columns[col.id].length === 0 && (
                                <div className="py-10 text-center text-sm text-slate-400">
                                    No hay comandas
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}
