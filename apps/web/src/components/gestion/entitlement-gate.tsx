'use client';

import { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

import { useEntitlements } from '@/features/gestion/hooks';
import { UpgradeBlock } from './upgrade-prompt';

interface EntitlementGateProps {
    children: ReactNode;
    entitlement: string;
    feature: string;
    plan: string;
    description?: string;
    loadingFallback?: ReactNode;
}

/**
 * Componente que valida si el business tiene el entitlement necesario
 * para mostrar el contenido. Si no lo tiene, muestra un prompt de upgrade.
 */
export function EntitlementGate({
    children,
    entitlement,
    feature,
    plan,
    description,
    loadingFallback,
}: EntitlementGateProps) {
    const { hasEntitlement, isLoading } = useEntitlements();

    if (isLoading) {
        return (
            loadingFallback ?? (
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                </div>
            )
        );
    }

    if (!hasEntitlement(entitlement)) {
        return <UpgradeBlock feature={feature} plan={plan} description={description} />;
    }

    return <>{children}</>;
}

interface ConditionalFeatureProps {
    children: ReactNode;
    entitlement: string;
    fallback?: ReactNode;
}

/**
 * Componente que muestra u oculta contenido basado en entitlements.
 * Útil para ocultar botones, secciones, etc.
 */
export function ConditionalFeature({ children, entitlement, fallback }: ConditionalFeatureProps) {
    const { hasEntitlement, isLoading } = useEntitlements();

    if (isLoading) {
        return null;
    }

    if (!hasEntitlement(entitlement)) {
        return fallback ? <>{fallback}</> : null;
    }

    return <>{children}</>;
}
