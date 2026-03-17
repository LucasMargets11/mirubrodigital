"use client";

import { usePendingQuotesSummary } from '@/features/gestion/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ArrowRight, CircleDollarSign } from 'lucide-react';
import { formatNumber } from '@/lib/format';

type PipelineBlockProps = {
    quotesEnabled: boolean;
};

export function PipelineBlock({ quotesEnabled }: PipelineBlockProps) {
    const quotesQuery = usePendingQuotesSummary(quotesEnabled);
    
    // Adapt to API response
    const count = quotesQuery.data?.count ?? 0;

    if (!quotesEnabled) return null;

    return (
        <Card className="col-span-1 border-blue-50 bg-blue-50/10">
            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-blue-100/50">
                <CardTitle className="text-base font-semibold text-blue-900 flex items-center gap-2">
                    <CircleDollarSign className="h-5 w-5 text-blue-600" />
                    Presupuestos
                </CardTitle>
                <Button variant="ghost" size="sm" asChild className="text-blue-600 hover:text-blue-800 hover:bg-blue-50">
                    <Link href="/app/gestion/ventas/presupuestos">
                        Ver todos <ArrowRight className="ml-1 h-3 w-3" />
                    </Link>
                </Button>
            </CardHeader>
            <CardContent className="pt-6 grid grid-cols-1 gap-4">
                <div className="space-y-1">
                    <p className="text-sm font-medium text-blue-600/80">Pendientes de respuesta</p>
                    <div className="flex items-baseline gap-2">
                        <p className="text-2xl font-bold text-blue-900">{formatNumber(count)}</p>
                        <span className="text-sm text-blue-700">activos</span>
                    </div>
                </div>
                
                <div className="text-xs text-blue-500 bg-white/50 p-3 rounded-lg border border-blue-100/50">
                    Los presupuestos vencen automáticamente según la configuración comercial. Revisar el estado para cerrar ventas.
                </div>
            </CardContent>
        </Card>
    );
}
