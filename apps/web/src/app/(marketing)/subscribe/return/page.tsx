'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { getClientApiBaseUrl } from '@/lib/api-url';
import { Loader2 } from 'lucide-react';

function ReturnContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const intentId = searchParams.get('intent_id');
    const [status, setStatus] = useState('Verificando estado del pago...');
    const [isPolling, setIsPolling] = useState(true);

    useEffect(() => {
        if (!intentId) {
            setStatus('No se encontró información del pago.');
            setIsPolling(false);
            return;
        }
        
        const baseUrl = getClientApiBaseUrl();
        const interval = setInterval(async () => {
             try {
                 const res = await fetch(`${baseUrl}/api/v1/billing/intent-status?intent_id=${intentId}`);
                 if (res.ok) {
                     const data = await res.json();
                     if (data.active) {
                         clearInterval(interval);
                         setStatus('Pago confirmado. Redirigiendo...');
                         setTimeout(() => {
                             router.push('/entrar');
                         }, 1000);
                     } else if (data.status === 'failed') {
                         setStatus('El pago ha fallado. Por favor intenta nuevamente.');
                         setIsPolling(false);
                         clearInterval(interval);
                     }
                 }
             } catch (e) {
                 console.error(e);
             }
        }, 2000);
        
        // Timeout after 60s
        const timeout = setTimeout(() => {
             clearInterval(interval);
             if (status.includes('Verificando')) {
                 setStatus('La verificación está tomando más tiempo de lo esperado. Te enviaremos un email cuando tu cuenta esté activa.');
                 setIsPolling(false);
             }
        }, 60000);
        
        return () => {
            clearInterval(interval);
            clearTimeout(timeout);
        };
    }, [intentId, router]);

    return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
            {isPolling && <Loader2 className="w-8 h-8 animate-spin text-brand-600" />}
            <h1 className="text-xl font-medium text-slate-900">{status}</h1>
            {!isPolling && intentId && (
                <button 
                    onClick={() => router.push('/pricing')}
                    className="text-brand-600 hover:underline"
                >
                    Volver a planes
                </button>
            )}
        </div>
    )
}

export default function ReturnPage() {
    return (
        <Suspense fallback={<div>Cargando...</div>}>
            <ReturnContent />
        </Suspense>
    )
}
