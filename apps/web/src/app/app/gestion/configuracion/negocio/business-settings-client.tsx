'use client';

import { useState } from 'react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { BillingProfileTab } from './billing-profile-tab';
import { BrandingTab } from './branding-tab';
import { DocumentSeriesTab } from './document-series-tab';

export function BusinessSettingsClient() {
    const [activeTab, setActiveTab] = useState('billing');

    return (
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight text-slate-900">Configuración del Negocio</h1>
                <p className="mt-2 text-sm text-slate-600">
                    Administrá los datos fiscales, branding y series de documentos de tu negocio.
                </p>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} defaultValue="billing">
                <TabsList className="mb-8">
                    <TabsTrigger value="billing">Perfil Fiscal</TabsTrigger>
                    <TabsTrigger value="branding">Branding</TabsTrigger>
                    <TabsTrigger value="series">Series de Documentos</TabsTrigger>
                </TabsList>

                <TabsContent value="billing">
                    <BillingProfileTab />
                </TabsContent>

                <TabsContent value="branding">
                    <BrandingTab />
                </TabsContent>

                <TabsContent value="series">
                    <DocumentSeriesTab />
                </TabsContent>
            </Tabs>
        </div>
    );
}
