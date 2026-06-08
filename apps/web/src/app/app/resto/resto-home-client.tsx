'use client';

import Link from 'next/link';
import type { Route } from 'next';
import {
    ClipboardList,
    ChefHat,
    QrCode,
    Star,
    Wallet,
    Settings,
    Utensils,
    Plus,
    CreditCard,
    DollarSign,
    HandCoins,
    UtensilsCrossed,
    ArrowRight,
    AlertTriangle,
    CheckCircle2,
    CircleAlert,
    type LucideIcon,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useCashSummary } from '@/features/cash/hooks';
import {
    getEffectiveRestaurantOperationSettings,
    useRestaurantOperationSettings,
} from '@/features/resto/hooks';
import { KpiCard } from '@/app/app/gestion/dashboard/components/owner/kpi-card';

type RestoHomePermissions = {
    canViewOrders: boolean;
    canViewKitchen: boolean;
    canViewCash: boolean;
    canViewMenu: boolean;
    canManageReviews: boolean;
    canManageSettings: boolean;
    canViewReports: boolean;
};

type RestoHomeFeatures = {
    orders: boolean;
    kitchen: boolean;
    menu: boolean;
    cash: boolean;
    reviews: boolean;
    reports: boolean;
};

type RestoHomeClientProps = {
    businessName: string;
    businessStatus: string;
    planName: string;
    permissions: RestoHomePermissions;
    features: RestoHomeFeatures;
    menuPublished: boolean | null;
};

type ModuleStatusTone = 'active' | 'inactive' | 'pending' | 'published' | 'unpublished';

const MODULE_BADGE_STYLES: Record<ModuleStatusTone, string> = {
    active: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
    inactive: 'bg-slate-100 text-slate-600 hover:bg-slate-100',
    pending: 'bg-amber-100 text-amber-700 hover:bg-amber-100',
    published: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
    unpublished: 'bg-amber-100 text-amber-700 hover:bg-amber-100',
};

function ModuleRow({
    icon: Icon,
    label,
    statusLabel,
    tone,
}: {
    icon: LucideIcon;
    label: string;
    statusLabel: string;
    tone: ModuleStatusTone;
}) {
    return (
        <div className="flex items-center gap-3 px-4 py-3">
            <Icon className="h-4 w-4 shrink-0 text-slate-400" />
            <span className="flex-1 text-sm font-medium text-slate-700">{label}</span>
            <Badge className={cn('border-transparent', MODULE_BADGE_STYLES[tone])}>{statusLabel}</Badge>
        </div>
    );
}

type OperationalAlert = {
    id: string;
    title: string;
    description: string;
    href: string;
    icon: LucideIcon;
};

export function RestoHomeClient({
    businessName,
    businessStatus,
    planName,
    permissions,
    features,
    menuPublished,
}: RestoHomeClientProps) {
    const operationSettingsQuery = useRestaurantOperationSettings({ enabled: true });
    const settings = getEffectiveRestaurantOperationSettings(operationSettingsQuery.data);

    const cashEnabled = features.cash && permissions.canViewCash;
    const cashQuery = useCashSummary(undefined, cashEnabled);
    const cashKnown = cashEnabled && !cashQuery.isLoading;
    const isCashOpen = Boolean(cashQuery.data?.session);

    const kitchenActive = features.kitchen && settings.kitchen_enabled;
    const tablesActive = features.orders && settings.tables_enabled;

    // ── Alertas operativas (solo si el dato existe) ──────────────────────────
    const alerts: OperationalAlert[] = [];
    if (cashKnown && !isCashOpen) {
        alerts.push({
            id: 'cash-closed',
            title: 'La caja está cerrada',
            description: 'Abrí la caja para comenzar a operar',
            href: '/app/operacion/caja',
            icon: CircleAlert,
        });
    }
    if (features.menu && menuPublished === false) {
        alerts.push({
            id: 'menu-unpublished',
            title: 'La carta no está publicada',
            description: 'Publicá tu carta para compartir el QR',
            href: '/app/carta/publicacion',
            icon: AlertTriangle,
        });
    }
    if (features.kitchen && !settings.kitchen_enabled) {
        alerts.push({
            id: 'kitchen-off',
            title: 'Cocina desactivada',
            description: 'La cocina en vivo está pausada en la operación',
            href: '/app/resto/settings/operation',
            icon: AlertTriangle,
        });
    }
    if (features.orders && !settings.tables_enabled) {
        alerts.push({
            id: 'tables-off',
            title: 'Mesas desactivadas',
            description: 'El servicio de mesas está pausado en la operación',
            href: '/app/resto/settings/operation',
            icon: AlertTriangle,
        });
    }

    const statusOk = businessStatus === 'active' || businessStatus === 'trialing';

    // ── Accesos rápidos (herramientas) ───────────────────────────────────────
    const tools: Array<{ href: string; label: string; icon: LucideIcon; show: boolean }> = [
        { href: '/app/orders/new', label: 'Nueva orden', icon: Plus, show: features.orders && permissions.canViewOrders },
        { href: '/app/kitchen', label: 'Cocina en vivo', icon: ChefHat, show: kitchenActive && permissions.canViewKitchen },
        { href: '/app/orders', label: 'POS', icon: ClipboardList, show: features.orders && permissions.canViewOrders },
        { href: '/app/operacion/caja', label: 'Caja', icon: Wallet, show: features.cash && permissions.canViewCash },
        { href: '/app/carta/productos', label: 'Carta Online', icon: Utensils, show: features.menu && permissions.canViewMenu },
        { href: '/app/resenas/qr', label: 'QR de Reseñas', icon: Star, show: features.reviews && permissions.canManageReviews },
        { href: '/app/resto/settings/operation', label: 'Config. operativa', icon: Settings, show: permissions.canManageSettings },
    ];
    const visibleTools = tools.filter((tool) => tool.show);

    return (
        <div className="space-y-8 p-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* ── Header ─────────────────────────────────────────────── */}
            <div className="flex flex-col gap-4 border-b border-gray-100 pb-6 md:flex-row md:items-end md:justify-between">
                <div className="space-y-1">
                    <div className="flex items-center gap-2">
                        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Restaurante Inteligente</h1>
                        <span
                            className={cn(
                                'rounded-full px-2.5 py-0.5 text-xs font-medium',
                                statusOk ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700',
                            )}
                        >
                            {planName}
                        </span>
                    </div>
                    <p className="text-sm text-slate-500">
                        Gestioná la operación diaria de tu restaurante desde un solo lugar.
                    </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    {features.orders && permissions.canViewOrders && (
                        <Button asChild>
                            <Link href={'/app/orders/new' as Route}>
                                <Plus className="mr-1.5 h-4 w-4" />
                                Nueva orden
                            </Link>
                        </Button>
                    )}
                    {features.orders && permissions.canViewOrders && (
                        <Button asChild variant="outline">
                            <Link href={'/app/orders' as Route}>Abrir POS</Link>
                        </Button>
                    )}
                    {permissions.canManageSettings && (
                        <Button asChild variant="outline">
                            <Link href={'/app/resto/settings/operation' as Route}>Configuración operativa</Link>
                        </Button>
                    )}
                </div>
            </div>

            {/* ── KPI Strip ──────────────────────────────────────────── */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                <KpiCard
                    title="Órdenes abiertas"
                    value="—"
                    subValue="Próximamente"
                    icon={ClipboardList}
                    tone="default"
                    href={features.orders && permissions.canViewOrders ? '/app/orders' : undefined}
                />
                <KpiCard
                    title="Pendientes de cobro"
                    value="—"
                    subValue="Próximamente"
                    icon={HandCoins}
                    tone="default"
                />
                <KpiCard
                    title="En cocina"
                    value={kitchenActive ? 'Activa' : 'Pausada'}
                    icon={UtensilsCrossed}
                    tone={kitchenActive ? 'success' : 'default'}
                    href={kitchenActive && permissions.canViewKitchen ? '/app/kitchen' : undefined}
                />
                <KpiCard
                    title="Ventas del día"
                    value="—"
                    subValue="Próximamente"
                    icon={DollarSign}
                    tone="default"
                />
                <KpiCard
                    title="Caja"
                    value={cashEnabled ? (cashKnown ? (isCashOpen ? 'Abierta' : 'Cerrada') : '…') : '—'}
                    subValue={cashEnabled ? undefined : 'No incluida'}
                    icon={CreditCard}
                    tone={cashEnabled && cashKnown ? (isCashOpen ? 'success' : 'warning') : 'default'}
                    href={features.cash && permissions.canViewCash ? '/app/operacion/caja' : undefined}
                    loading={cashEnabled && cashQuery.isLoading}
                />
                <KpiCard
                    title="Carta Online"
                    value={menuPublished === null ? '—' : menuPublished ? 'Publicada' : 'Pausada'}
                    subValue={menuPublished === null ? 'No disponible' : undefined}
                    icon={QrCode}
                    tone={menuPublished === null ? 'default' : menuPublished ? 'success' : 'warning'}
                    href={features.menu && permissions.canViewMenu ? '/app/carta/publicacion' : undefined}
                />
            </div>

            {/* ── Two-column layout ──────────────────────────────────── */}
            <div className="grid grid-cols-1 gap-8 xl:grid-cols-3">
                {/* Left column */}
                <div className="space-y-8 xl:col-span-2">
                    {/* Herramientas del restaurante */}
                    {visibleTools.length > 0 && (
                        <Card>
                            <CardHeader className="pb-3 border-b border-slate-100">
                                <CardTitle className="text-base font-semibold text-slate-800">
                                    Herramientas del restaurante
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                                {visibleTools.map((tool) => (
                                    <Button
                                        key={tool.href}
                                        variant="outline"
                                        className="h-auto flex-col gap-2 py-4 border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:text-slate-900 hover:border-slate-300"
                                        asChild
                                    >
                                        <Link href={tool.href as Route}>
                                            <tool.icon className="h-5 w-5" />
                                            <span className="text-xs font-semibold">{tool.label}</span>
                                        </Link>
                                    </Button>
                                ))}
                            </CardContent>
                        </Card>
                    )}

                    {/* Operación de hoy */}
                    <Card>
                        <CardHeader className="pb-3 border-b border-slate-100">
                            <CardTitle className="text-base font-semibold text-slate-800">Operación de hoy</CardTitle>
                        </CardHeader>
                        <CardContent className="p-4">
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                                {[
                                    'Órdenes abiertas',
                                    'Pedidos en cocina',
                                    'Listas / retiradas',
                                    'Pendientes de cobro',
                                ].map((metric) => (
                                    <div
                                        key={metric}
                                        className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4"
                                    >
                                        <p className="text-xs font-medium text-slate-500">{metric}</p>
                                        <p className="mt-1 text-sm font-semibold text-slate-400">No disponible todavía</p>
                                    </div>
                                ))}
                            </div>
                            {features.orders && permissions.canViewOrders && (
                                <div className="mt-4 flex justify-end">
                                    <Link
                                        href={'/app/orders' as Route}
                                        className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-600 hover:text-brand-700"
                                    >
                                        Ver órdenes
                                        <ArrowRight className="h-4 w-4" />
                                    </Link>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Right column */}
                <div className="space-y-8 xl:col-span-1">
                    {/* Estado de módulos */}
                    <Card className="overflow-hidden">
                        <CardHeader className="pb-2 border-b border-slate-100">
                            <CardTitle className="text-base font-semibold text-slate-900">Estado de módulos</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-slate-100">
                                <ModuleRow
                                    icon={ClipboardList}
                                    label="Mesas"
                                    statusLabel={tablesActive ? 'Activas' : 'Desactivadas'}
                                    tone={tablesActive ? 'active' : 'inactive'}
                                />
                                <ModuleRow
                                    icon={ChefHat}
                                    label="Cocina"
                                    statusLabel={kitchenActive ? 'Activa' : 'Desactivada'}
                                    tone={kitchenActive ? 'active' : 'inactive'}
                                />
                                <ModuleRow
                                    icon={Utensils}
                                    label="Carta Online"
                                    statusLabel={
                                        menuPublished === null
                                            ? 'Pendiente de configurar'
                                            : menuPublished
                                                ? 'Publicada'
                                                : 'No publicada'
                                    }
                                    tone={
                                        menuPublished === null
                                            ? 'pending'
                                            : menuPublished
                                                ? 'published'
                                                : 'unpublished'
                                    }
                                />
                                <ModuleRow
                                    icon={Star}
                                    label="QR de Reseñas"
                                    statusLabel={features.reviews ? 'Activo' : 'No incluido'}
                                    tone={features.reviews ? 'active' : 'inactive'}
                                />
                                <ModuleRow
                                    icon={Wallet}
                                    label="Caja"
                                    statusLabel={cashEnabled ? (cashKnown ? (isCashOpen ? 'Abierta' : 'Cerrada') : '—') : 'No incluida'}
                                    tone={cashEnabled && cashKnown ? (isCashOpen ? 'active' : 'pending') : 'inactive'}
                                />
                            </div>
                        </CardContent>
                    </Card>

                    {/* Alertas operativas */}
                    {alerts.length === 0 ? (
                        <Card className="border-slate-100 bg-slate-50/50">
                            <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                                <div className="mb-2 rounded-full bg-emerald-100 p-2">
                                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                                </div>
                                <p className="font-medium text-slate-900">Sin alertas activas</p>
                                <p className="mt-0.5 text-xs text-slate-500">Todo en orden por ahora.</p>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card className="overflow-hidden border-amber-200">
                            <CardHeader className="pb-2 border-b border-slate-100">
                                <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900">
                                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                                    Alertas operativas
                                    <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                                        {alerts.length}
                                    </span>
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="divide-y divide-slate-100">
                                    {alerts.map((alert) => {
                                        const Icon = alert.icon;
                                        return (
                                            <Link
                                                key={alert.id}
                                                href={alert.href as Route}
                                                className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-amber-50/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-300"
                                            >
                                                <Icon className="h-4 w-4 shrink-0 text-amber-500" />
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate text-sm font-medium text-slate-900">{alert.title}</p>
                                                    <p className="truncate text-xs text-slate-500">{alert.description}</p>
                                                </div>
                                                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5" />
                                            </Link>
                                        );
                                    })}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </div>
    );
}
