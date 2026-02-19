import { AlertCircle, Sparkles } from 'lucide-react';
import Link from 'next/link';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

interface UpgradePromptProps {
    feature: string;
    plan: string;
    description?: string;
    className?: string;
}

export function UpgradePrompt({ feature, plan, description, className }: UpgradePromptProps) {
    return (
        <div className={className}>
            <Alert variant="default" className="border-blue-200 bg-blue-50">
                <AlertCircle className="h-4 w-4 text-blue-600" />
                <AlertTitle className="text-blue-900">
                    Esta funcionalidad requiere actualización
                </AlertTitle>
                <AlertDescription className="text-blue-800">
                    <div className="mt-2 space-y-3">
                        <p>
                            <strong>{feature}</strong> no está incluido en tu plan actual.
                            {description && ` ${description}`}
                        </p>
                        <p className="text-sm">
                            Actualiza a <strong>{plan}</strong> para acceder a esta funcionalidad.
                        </p>
                        <div className="flex gap-2 mt-4">
                            <Button asChild size="sm" className="gap-2">
                                <Link href="/app/settings/billing">
                                    <Sparkles className="h-4 w-4" />
                                    Actualizar Plan
                                </Link>
                            </Button>
                            <Button asChild variant="outline" size="sm">
                                <Link href="/pricing">Ver Planes</Link>
                            </Button>
                        </div>
                    </div>
                </AlertDescription>
            </Alert>
        </div>
    );
}

interface UpgradeBlockProps {
    feature: string;
    plan: string;
    description?: string;
}

export function UpgradeBlock({ feature, plan, description }: UpgradeBlockProps) {
    return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
            <div className="max-w-md text-center space-y-4">
                <div className="mx-auto w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center">
                    <Sparkles className="h-8 w-8 text-blue-600" />
                </div>
                <div className="space-y-2">
                    <h3 className="text-xl font-semibold text-gray-900">{feature}</h3>
                    <p className="text-gray-600">
                        Esta funcionalidad requiere el plan <strong>{plan}</strong>.
                        {description && ` ${description}`}
                    </p>
                </div>
                <div className="flex gap-2 justify-center mt-6">
                    <Button asChild className="gap-2">
                        <Link href="/app/settings/billing">
                            <Sparkles className="h-4 w-4" />
                            Actualizar a {plan}
                        </Link>
                    </Button>
                    <Button asChild variant="outline">
                        <Link href="/pricing">Ver Planes</Link>
                    </Button>
                </div>
            </div>
        </div>
    );
}
