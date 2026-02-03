'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getClientApiBaseUrl } from '@/lib/api-url';

function SubscribeForm() {
    const searchParams = useSearchParams();
    const planCode = searchParams.get('plan_code') || searchParams.get('bundle_code');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        setLoading(true);
        setError('');
        
        const formData = new FormData(e.currentTarget);
        const data = Object.fromEntries(formData);
        
        try {
            const baseUrl = getClientApiBaseUrl();
            const res = await fetch(`${baseUrl}/api/v1/billing/start-subscription`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...data, plan_code: planCode }),
            });
            
            const json = await res.json();
            
            if (!res.ok) {
                throw new Error(json.error || 'Something went wrong');
            }
            
            window.location.href = json.init_point;
            
        } catch (err: any) {
             setError(err.message);
             setLoading(false);
        }
    }

    if (!planCode) return <div className="p-10 text-center">No plan selected</div>;

    return (
        <div className="max-w-md mx-auto py-10 px-4">
            <h1 className="text-2xl font-bold mb-6">Suscribirse</h1>
            <form onSubmit={onSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="business_name">Nombre del Negocio</Label>
                  <Input id="business_name" name="business_name" required placeholder="Mi Negocio S.A." />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" name="email" type="email" required placeholder="tu@email.com" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Contraseña</Label>
                  <Input id="password" name="password" type="password" required />
                </div>
                
                {error && (
                    <div className="p-3 text-sm text-red-500 bg-red-50 rounded-md">
                        {error}
                    </div>
                )}
                
                <Button type="submit" className="w-full" disabled={loading}>
                     {loading ? 'Procesando...' : 'Ir a Pagar con MercadoPago'}
                </Button>
            </form>
        </div>
    )
}

export default function SubscribePage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <SubscribeForm />
        </Suspense>
    )
}
