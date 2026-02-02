'use client';

import { CheckCircle2, Clock, ShoppingBag, Truck, Utensils, XCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { KitchenItem, KitchenOrder, KitchenStatus } from '@/features/orders/types';
import { cn } from '@/lib/utils';

interface KitchenTicketProps {
    order: KitchenOrder;
    onUpdateItem: (itemId: string, status: KitchenStatus) => void;
    onUpdateOrder: (orderId: string, status: KitchenStatus) => void;
}

export function KitchenTicket({ order, onUpdateItem, onUpdateOrder }: KitchenTicketProps) {
    const elapsed = order.elapsed_seconds;
    const isLate = elapsed > 600; // 10 mins
    const isVeryLate = elapsed > 900; // 15 mins

    const minutes = Math.floor(elapsed / 60);
    const timeDisplay = minutes > 0 ? `${minutes} min` : 'Ahora';

    const getChannelIcon = () => {
        switch (order.channel) {
            case 'delivery':
                return <Truck className="h-3 w-3" />;
            case 'pickup':
                return <ShoppingBag className="h-3 w-3" />;
            default:
                return <Utensils className="h-3 w-3" />;
        }
    };

    const handleItemClick = (item: KitchenItem) => {
        let next: KitchenStatus = 'pending';
        if (item.kitchen_status === 'pending') next = 'in_progress';
        else if (item.kitchen_status === 'in_progress') next = 'ready';
        else if (item.kitchen_status === 'ready') next = 'done';
        
        if (item.kitchen_status !== 'done') {
            onUpdateItem(item.id, next);
        }
    };

    const renderModifiers = (modifiers: unknown[]) => {
        if (!modifiers || !Array.isArray(modifiers) || modifiers.length === 0) return null;
        return (
            <div className="mt-1 border-l-2 border-slate-200 pl-2 text-xs text-slate-500">
                {modifiers.map((mod, idx) => (
                    <div key={idx}>
                         {typeof mod === 'string' ? mod : (mod as any).name || JSON.stringify(mod)}
                    </div>
                ))}
            </div>
        );
    };

    return (
        <Card
            className={cn(
                'flex h-full flex-col border-l-4 shadow-sm transition-all hover:shadow-md',
                isVeryLate
                    ? 'border-l-red-500'
                    : isLate
                      ? 'border-l-yellow-500'
                      : 'border-l-blue-500'
            )}
        >
            <CardHeader className="space-y-0 p-3 pb-2">
                <div className="flex items-start justify-between">
                    <div className="text-lg font-bold leading-tight text-slate-900">
                        {order.table_name || order.customer_name || `#${order.number}`}
                    </div>
                    <Badge variant={isVeryLate ? 'destructive' : 'secondary'} className="text-xs">
                        <Clock className="mr-1 h-3 w-3" />
                        {timeDisplay}
                    </Badge>
                </div>
                <div className="mt-1 flex items-center gap-2">
                    <Badge variant="outline" className="h-5 gap-1 px-1 py-0 text-[10px]">
                        {getChannelIcon()}
                        {order.channel_display}
                    </Badge>
                    <span className="text-xs text-slate-400">#{order.number}</span>
                </div>
            </CardHeader>
            <Separator />
            <CardContent className="flex-1 overflow-y-auto bg-slate-50/50 p-3">
                {order.note && (
                    <div className="mb-3 rounded border border-yellow-100 bg-yellow-50 p-2 text-xs text-yellow-800">
                        Nota: {order.note}
                    </div>
                )}
                <div className="space-y-2">
                    {order.items.map((item) => (
                        <div
                            key={item.id}
                            className={cn(
                                'cursor-pointer rounded border p-2 text-sm transition-colors',
                                item.kitchen_status === 'done'
                                    ? 'bg-slate-100 text-slate-500 opacity-60'
                                    : 'bg-white shadow-sm',
                                item.kitchen_status === 'pending'
                                    ? 'border-orange-200 hover:bg-orange-50'
                                    : item.kitchen_status === 'in_progress'
                                      ? 'border-blue-200 hover:bg-blue-50'
                                      : item.kitchen_status === 'ready'
                                        ? 'border-emerald-200 hover:bg-emerald-50'
                                        : 'border-slate-200'
                            )}
                            onClick={() => handleItemClick(item)}
                        >
                            <div className="flex justify-between">
                                <span
                                    className={cn(
                                        'font-medium',
                                        item.kitchen_status === 'done' && 'line-through'
                                    )}
                                >
                                    {Number(item.quantity) > 1 && (
                                        <span className="mr-1 inline-flex items-center justify-center rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-600">
                                            {Number(item.quantity)}x
                                        </span>
                                    )}
                                    {item.name}
                                </span>
                                {item.kitchen_status === 'done' && <CheckCircle2 className="h-4 w-4 text-slate-400" />}
                            </div>
                            {renderModifiers(item.modifiers)}
                            {item.note && <div className="mt-1 text-xs italic text-slate-500">"{item.note}"</div>}
                        </div>
                    ))}
                </div>
            </CardContent>
            <CardFooter className="border-t bg-white p-2">
                <Button
                    className="h-8 w-full text-xs"
                    variant="outline"
                    onClick={() => onUpdateOrder(order.id, 'ready')}
                >
                    Marcar todo listo
                </Button>
            </CardFooter>
        </Card>
    );
}
