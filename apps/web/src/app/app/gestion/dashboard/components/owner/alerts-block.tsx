"use client";

import { useInventorySummary } from '@/features/gestion/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, Diamond } from 'lucide-react';
import type { InventorySummaryStats } from '@/features/gestion/types';

type AlertsBlockProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
};

export function AlertsBlock({ inventorySummary, canViewStock }: AlertsBlockProps) {
    if (!canViewStock) return null;

    const lowStock = inventorySummary?.low_stock ?? 0;
    const outStock = inventorySummary?.out_of_stock ?? 0;
    const totalWarnings = lowStock + outStock;

    if (totalWarnings === 0) {
        return (
            <Card className="border-slate-100 bg-slate-50/50">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                    <div className="rounded-full bg-emerald-100 p-2 mb-2">
                        <Diamond className="h-5 w-5 text-emerald-600" />
                    </div>
                    <p className="font-medium text-slate-900">Sin alertas críticas</p>
                    <p className="text-xs text-slate-500">Tu inventario está saludable.</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border-amber-100 bg-amber-50/30">
            <CardHeader className="pb-2 border-b border-amber-100">
                <CardTitle className="text-base font-semibold text-amber-900 flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-amber-600" />
                    Alertas
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="divide-y divide-amber-100/50">
                    {outStock > 0 && (
                        <div className="flex items-center justify-between p-4">
                            <span className="text-sm font-medium text-amber-900">Sin stock</span>
                            <span className="text-sm font-bold text-amber-700">{outStock} productos</span>
                        </div>
                    )}
                    {lowStock > 0 && (
                        <div className="flex items-center justify-between p-4">
                            <span className="text-sm font-medium text-amber-800">Stock bajo</span>
                            <span className="text-sm font-bold text-amber-600">{lowStock} productos</span>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
