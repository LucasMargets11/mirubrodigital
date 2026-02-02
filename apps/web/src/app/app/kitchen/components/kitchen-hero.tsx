'use client';

import { RefreshCw, Wifi, WifiOff } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';

interface KitchenHeroProps {
    metrics: {
        pending: number;
        inProgress: number;
        ready: number;
    };
    isConnected: boolean;
    isUpdating: boolean;
    lastUpdated?: Date;
    onRefresh: () => void;
    autoRefresh: boolean;
    toggleAutoRefresh: () => void;
}

export function KitchenHero({
    metrics,
    isConnected,
    isUpdating,
    lastUpdated,
    onRefresh,
    autoRefresh,
    toggleAutoRefresh,
}: KitchenHeroProps) {
    return (
        <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
                <div className="flex flex-col">
                    <h1 className="text-xl font-bold text-slate-900">Cocina en Vivo</h1>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                        {isConnected ? (
                            <span className="flex items-center gap-1 text-emerald-600">
                                <Wifi className="h-3 w-3" /> Conectado
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-red-600">
                                <WifiOff className="h-3 w-3" /> Sin conexión
                            </span>
                        )}
                        <span>•</span>
                        <span>{lastUpdated ? `Actualizado ${lastUpdated.toLocaleTimeString()}` : 'Cargando...'}</span>
                    </div>
                </div>

                <div className="hidden h-8 w-px bg-slate-200 sm:block" />

                <div className="flex gap-2">
                    <Badge variant="outline" className="border-orange-200 bg-orange-50 text-orange-700">
                        Pend: {metrics.pending}
                    </Badge>
                    <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
                        Prep: {metrics.inProgress}
                    </Badge>
                    <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                        Listos: {metrics.ready}
                    </Badge>
                </div>
            </div>

            <div className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">Auto</span>
                    <Switch checked={autoRefresh} onCheckedChange={toggleAutoRefresh} />
                </div>
                <Button
                    variant="outline"
                    size="icon"
                    onClick={onRefresh}
                    disabled={isUpdating}
                    className={isUpdating ? 'animate-spin' : ''}
                >
                    <RefreshCw className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
}
