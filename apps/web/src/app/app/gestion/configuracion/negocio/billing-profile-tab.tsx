'use client';

import { useEffect, useRef, useState } from 'react';

import { Card } from '@/components/ui/card';
import { ToastBubble } from '@/components/app/toast';
import { useBusinessBillingProfileQuery, useUpdateBusinessBillingProfileMutation } from '@/features/gestion/hooks';
import type { BusinessBillingProfilePayload, TaxIdType, VatCondition } from '@/features/gestion/types';
import { cn } from '@/lib/utils';

type ToastState = { message: string; tone: 'success' | 'error' };

const TAX_ID_TYPE_OPTIONS: { value: TaxIdType; label: string }[] = [
    { value: 'cuit', label: 'CUIT' },
    { value: 'cuil', label: 'CUIL' },
    { value: 'dni', label: 'DNI' },
    { value: 'other', label: 'Otro' },
];

const VAT_CONDITION_OPTIONS: { value: VatCondition; label: string }[] = [
    { value: 'responsable_inscripto', label: 'Responsable Inscripto' },
    { value: 'monotributo', label: 'Monotributo' },
    { value: 'exento', label: 'Exento' },
    { value: 'consumidor_final', label: 'Consumidor Final' },
    { value: 'no_responsable', label: 'No Responsable' },
];

export function BillingProfileTab() {
    const profileQuery = useBusinessBillingProfileQuery();
    const updateProfile = useUpdateBusinessBillingProfileMutation();
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const [formData, setFormData] = useState<BusinessBillingProfilePayload>({
        legal_name: '',
        trade_name: '',
        tax_id_type: 'cuit',
        tax_id: '',
        vat_condition: 'responsable_inscripto',
        iibb: '',
        activity_start_date: null,
        commercial_address: '',
        fiscal_address: '',
        phone: '',
        email: '',
        website: '',
    });

    useEffect(() => {
        if (profileQuery.data) {
            setFormData({
                legal_name: profileQuery.data.legal_name || '',
                trade_name: profileQuery.data.trade_name || '',
                tax_id_type: profileQuery.data.tax_id_type || 'cuit',
                tax_id: profileQuery.data.tax_id || '',
                vat_condition: profileQuery.data.vat_condition || 'responsable_inscripto',
                iibb: profileQuery.data.iibb || '',
                activity_start_date: profileQuery.data.activity_start_date || null,
                commercial_address: profileQuery.data.commercial_address || '',
                fiscal_address: profileQuery.data.fiscal_address || '',
                phone: profileQuery.data.phone || '',
                email: profileQuery.data.email || '',
                website: profileQuery.data.website || '',
            });
        }
    }, [profileQuery.data]);

    useEffect(() => {
        return () => {
            if (toastTimeoutRef.current) {
                clearTimeout(toastTimeoutRef.current);
            }
        };
    }, []);

    const showToast = (message: string, tone: 'success' | 'error' = 'success') => {
        if (toastTimeoutRef.current) {
            clearTimeout(toastTimeoutRef.current);
        }
        setToast({ message, tone });
        toastTimeoutRef.current = setTimeout(() => setToast(null), 3000);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // Validación básica
        if (!formData.legal_name || !formData.tax_id || !formData.commercial_address) {
            showToast('Completá los campos obligatorios', 'error');
            return;
        }

        try {
            await updateProfile.mutateAsync(formData);
            showToast('Perfil fiscal actualizado correctamente', 'success');
        } catch (error) {
            showToast('Error al actualizar el perfil fiscal', 'error');
            console.error(error);
        }
    };

    const handleChange = (field: keyof BusinessBillingProfilePayload, value: string) => {
        setFormData((prev) => ({ ...prev, [field]: value }));
    };

    if (profileQuery.isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-sm text-slate-500">Cargando...</div>
            </div>
        );
    }

    if (profileQuery.isError) {
        return (
            <div className="rounded-lg bg-red-50 p-4">
                <p className="text-sm text-red-800">Error al cargar el perfil fiscal. Intentá nuevamente.</p>
            </div>
        );
    }

    const isComplete = profileQuery.data?.is_complete ?? false;

    return (
        <>
            <Card className="p-6">
                <div className="mb-6">
                    <h2 className="text-xl font-semibold text-slate-900">Perfil Fiscal</h2>
                    <p className="mt-1 text-sm text-slate-600">
                        Configurá los datos legales y fiscales de tu negocio para generar comprobantes.
                    </p>
                    {!isComplete && (
                        <div className="mt-3 rounded-md bg-amber-50 p-3">
                            <p className="text-sm text-amber-800">
                                ⚠️ Completá los campos obligatorios para poder emitir documentos fiscales.
                            </p>
                        </div>
                    )}
                    {isComplete && (
                        <div className="mt-3 rounded-md bg-green-50 p-3">
                            <p className="text-sm text-green-800">✓ Perfil completo y listo para emitir documentos.</p>
                        </div>
                    )}
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                    {/* Datos Fiscales */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-medium text-slate-900">Datos Fiscales</h3>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label htmlFor="legal_name" className="block text-sm font-medium text-slate-700">
                                    Razón Social <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="text"
                                    id="legal_name"
                                    value={formData.legal_name}
                                    onChange={(e) => handleChange('legal_name', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                    required
                                />
                            </div>

                            <div>
                                <label htmlFor="trade_name" className="block text-sm font-medium text-slate-700">
                                    Nombre Comercial
                                </label>
                                <input
                                    type="text"
                                    id="trade_name"
                                    value={formData.trade_name}
                                    onChange={(e) => handleChange('trade_name', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                            </div>

                            <div>
                                <label htmlFor="tax_id_type" className="block text-sm font-medium text-slate-700">
                                    Tipo de Identificación <span className="text-red-500">*</span>
                                </label>
                                <select
                                    id="tax_id_type"
                                    value={formData.tax_id_type}
                                    onChange={(e) => handleChange('tax_id_type', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                    required
                                >
                                    {TAX_ID_TYPE_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label htmlFor="tax_id" className="block text-sm font-medium text-slate-700">
                                    {formData.tax_id_type?.toUpperCase() || 'CUIT'} <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="text"
                                    id="tax_id"
                                    value={formData.tax_id}
                                    onChange={(e) => handleChange('tax_id', e.target.value)}
                                    placeholder="XX-XXXXXXXX-X"
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                    required
                                />
                            </div>

                            <div>
                                <label htmlFor="vat_condition" className="block text-sm font-medium text-slate-700">
                                    Condición ante IVA <span className="text-red-500">*</span>
                                </label>
                                <select
                                    id="vat_condition"
                                    value={formData.vat_condition}
                                    onChange={(e) => handleChange('vat_condition', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                    required
                                >
                                    {VAT_CONDITION_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label htmlFor="iibb" className="block text-sm font-medium text-slate-700">
                                    Ingresos Brutos (IIBB)
                                </label>
                                <input
                                    type="text"
                                    id="iibb"
                                    value={formData.iibb}
                                    onChange={(e) => handleChange('iibb', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                            </div>

                            <div>
                                <label htmlFor="activity_start_date" className="block text-sm font-medium text-slate-700">
                                    Inicio de Actividades
                                </label>
                                <input
                                    type="date"
                                    id="activity_start_date"
                                    value={formData.activity_start_date || ''}
                                    onChange={(e) => handleChange('activity_start_date', e.target.value || null)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                            </div>
                        </div>
                    </div>

                    {/* Domicilios */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-medium text-slate-900">Domicilios</h3>

                        <div>
                            <label htmlFor="fiscal_address" className="block text-sm font-medium text-slate-700">
                                Domicilio Fiscal
                            </label>
                            <textarea
                                id="fiscal_address"
                                value={formData.fiscal_address}
                                onChange={(e) => handleChange('fiscal_address', e.target.value)}
                                rows={2}
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                            />
                        </div>

                        <div>
                            <label htmlFor="commercial_address" className="block text-sm font-medium text-slate-700">
                                Domicilio Comercial <span className="text-red-500">*</span>
                            </label>
                            <textarea
                                id="commercial_address"
                                value={formData.commercial_address}
                                onChange={(e) => handleChange('commercial_address', e.target.value)}
                                rows={2}
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                required
                            />
                            <p className="mt-1 text-xs text-slate-500">Aparecerá en facturas y presupuestos</p>
                        </div>
                    </div>

                    {/* Contacto */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-medium text-slate-900">Contacto</h3>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label htmlFor="phone" className="block text-sm font-medium text-slate-700">
                                    Teléfono
                                </label>
                                <input
                                    type="tel"
                                    id="phone"
                                    value={formData.phone}
                                    onChange={(e) => handleChange('phone', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                            </div>

                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                                    Email
                                </label>
                                <input
                                    type="email"
                                    id="email"
                                    value={formData.email}
                                    onChange={(e) => handleChange('email', e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                            </div>
                        </div>

                        <div>
                            <label htmlFor="website" className="block text-sm font-medium text-slate-700">
                                Sitio Web
                            </label>
                            <input
                                type="url"
                                id="website"
                                value={formData.website}
                                onChange={(e) => handleChange('website', e.target.value)}
                                placeholder="https://ejemplo.com"
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                            />
                        </div>
                    </div>

                    {/* Submit */}
                    <div className="flex items-center justify-end gap-3 border-t border-slate-200 pt-4">
                        <button
                            type="submit"
                            disabled={updateProfile.isPending}
                            className={cn(
                                'rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
                                updateProfile.isPending && 'cursor-not-allowed opacity-50'
                            )}
                        >
                            {updateProfile.isPending ? 'Guardando...' : 'Guardar Cambios'}
                        </button>
                    </div>
                </form>
            </Card>

            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </>
    );
}
