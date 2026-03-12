"use client";

import { useTopSellingProducts } from '@/features/gestion/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ArrowRight, Package, TrendingUp, AlertCircle, Loader2 } from 'lucide-react';
import { formatCurrency, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useMemo } from 'react';

type SalesTrendBlockProps = {
    canViewSales: boolean;
};

// Safe component to avoid crashes with robust error handling
export function SalesTrendBlock({ canViewSales }: SalesTrendBlockProps) {
    const { data, isLoading, isError } = useTopSellingProducts('7d', 5, canViewSales);
    
    // 1. Data Sanitization & Memoization
    const { processedItems, maxSales } = useMemo(() => {
        if (!data?.items || !Array.isArray(data.items)) {
            return { processedItems: [], maxSales: 0 };
        }

        const cleanItems = data.items
            .filter(item => item && (item.total_sales || item.total_qty)) // Remove nulls/zeros
            .map(item => ({
                id: item.product_id || Math.random().toString(36),
                name: item.name || 'Producto desconocido',
                qty: Number(item.total_qty) || 0,
                amount: Number(item.total_sales) || 0
            }))
            .sort((a, b) => b.amount - a.amount)
            .slice(0, 5); // Strict limit to 5 items

        const max = cleanItems.length > 0 ? cleanItems[0].amount : 0;

        return { processedItems: cleanItems, maxSales: max };
    }, [data]);

    // 2. Permission Check
    if (!canViewSales) return null;

    // 3. Loading State - Stable Height Container
    if (isLoading) {
        return (
            <Card className="col-span-1 border-slate-200 shadow-sm h-full min-h-[350px] flex items-center justify-center">
                <div className="flex flex-col items-center gap-2">
                    <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                    <p className="text-xs text-slate-400 font-medium">Cargando top productos...</p>
                </div>
            </Card>
        );
    }

    // 4. Error State
    if (isError) {
        return (
            <Card className="col-span-1 border-red-100 bg-red-50/10 h-full min-h-[350px] flex flex-col items-center justify-center p-6 text-center">
                <AlertCircle className="h-8 w-8 text-red-400 mb-2" />
                <p className="text-sm font-medium text-red-800">No se pudo cargar el ranking</p>
                <Button variant="link" className="text-red-500 h-auto p-0 text-xs mt-1" onClick={() => window.location.reload()}>
                    Reintentar
                </Button>
            </Card>
        );
    }

    // 5. Empty State
    if (processedItems.length === 0) {
        return (
            <Card className="col-span-1 border-slate-200 shadow-sm flex flex-col h-full min-h-[350px]">
                <CardHeader className="pb-2 border-b border-slate-100">
                    <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="h-5 w-5 text-indigo-600" />
                        Top Productos
                    </CardTitle>
                </CardHeader>
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                    <div className="rounded-full bg-slate-50 p-4 mb-3 border border-slate-100">
                        <Package className="h-6 w-6 text-slate-400" />
                    </div>
                    <h3 className="font-medium text-slate-900 text-sm">Sin ventas registradas</h3>
                    <p className="text-xs text-slate-500 mt-1 max-w-[200px]">
                        Los productos más vendidos aparecerán aquí cuando realices ventas.
                    </p>
                    <Button variant="outline" size="sm" asChild className="mt-4 h-8 text-xs border-indigo-200 hover:bg-indigo-50 text-indigo-700">
                        <Link href="/app/gestion/ventas/nueva">
                            Registrar venta
                        </Link>
                    </Button>
                </div>
            </Card>
        );
    }

    // 6. Success State - Ranking List
    return (
        <Card className="col-span-1 border-slate-200 shadow-sm flex flex-col h-full min-h-[350px] overflow-hidden">
             <CardHeader className="flex flex-row items-center justify-between py-3 px-4 border-b border-slate-100 bg-slate-50/50">
                <div className="space-y-0.5">
                    <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-indigo-600" />
                        Top Productos (7d)
                    </CardTitle>
                </div>
                <Button variant="ghost" size="sm" asChild className="h-7 px-2 text-xs text-slate-500 hover:text-indigo-700 hover:bg-indigo-50">
                    <Link href="/app/gestion/reportes">
                        Ver todo <ArrowRight className="ml-1 h-3 w-3" />
                    </Link>
                </Button>
            </CardHeader>
            <CardContent className="p-0 flex-1">
                <div className="divide-y divide-slate-100">
                    {processedItems.map((item, index) => {
                        const percentage = maxSales > 0 ? (item.amount / maxSales) * 100 : 0;
                        const isTop = index === 0;

                        return (
                            <div key={item.id} className="relative group hover:bg-slate-50/80 transition-colors p-3">
                                {/* Row Content */}
                                <div className="flex items-start gap-3 relative z-10 w-full">
                                    {/* Rank Badge */}
                                    <div className={cn(
                                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold border shadow-sm mt-0.5",
                                        isTop 
                                            ? "bg-amber-100 text-amber-700 border-amber-200" 
                                            : "bg-white text-slate-500 border-slate-200"
                                    )}>
                                        {index + 1}
                                    </div>
                                    
                                    {/* Product Info */}
                                    <div className="flex-1 min-w-0 flex flex-col gap-1">
                                        <div className="flex justify-between items-center gap-4">
                                            <p 
                                                className="truncate text-sm font-medium text-slate-700 group-hover:text-slate-900 transition-colors"
                                                title={item.name}
                                            >
                                                {item.name}
                                            </p>
                                            <span className="text-sm font-bold text-slate-900 shrink-0">
                                                {formatCurrency(item.amount)}
                                            </span>
                                        </div>

                                        <div className="flex justify-between items-center text-xs text-slate-500">
                                            <span className="flex items-center gap-1">
                                                <Package className="h-3 w-3" />
                                                {formatNumber(item.qty)} u.
                                            </span>
                                            
                                            {/* Progress Bar Container */}
                                            <div className="w-24 h-1.5 bg-slate-100 rounded-full overflow-hidden ml-auto">
                                                <div 
                                                    className={cn(
                                                        "h-full rounded-full transition-all duration-500 ease-out",
                                                        isTop ? "bg-gradient-to-r from-amber-400 to-orange-500" : "bg-indigo-500"
                                                    )}
                                                    style={{ width: `${percentage}%` }}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </CardContent>
            {/* Footer Summary */}
            <div className="bg-slate-50 border-t border-slate-100 p-3 text-xs text-center text-slate-500">
                Mostrando top 5 de ventas recientes
            </div>
        </Card>
    );
}