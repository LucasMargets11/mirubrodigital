'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';

import { Card } from '@/components/ui/card';
import { ToastBubble } from '@/components/app/toast';
import {
    useBusinessBrandingQuery,
    useUpdateBusinessBrandingMutation,
    useUploadBusinessLogoMutation,
} from '@/features/gestion/hooks';
import { cn } from '@/lib/utils';

type ToastState = { message: string; tone: 'success' | 'error' };

export function BrandingTab() {
    const brandingQuery = useBusinessBrandingQuery();
    const updateBranding = useUpdateBusinessBrandingMutation();
    const uploadLogo = useUploadBusinessLogoMutation();
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const [accentColor, setAccentColor] = useState('#000000');
    const [horizontalPreview, setHorizontalPreview] = useState<string | null>(null);
    const [squarePreview, setSquarePreview] = useState<string | null>(null);

    useEffect(() => {
        if (brandingQuery.data) {
            setAccentColor(brandingQuery.data.accent_color || '#000000');
        }
    }, [brandingQuery.data]);

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

    const handleColorChange = async () => {
        try {
            await updateBranding.mutateAsync({ accent_color: accentColor });
            showToast('Color corporativo actualizado', 'success');
        } catch (error) {
            showToast('Error al actualizar el color', 'error');
            console.error(error);
        }
    };

    const handleLogoUpload = async (file: File, type: 'horizontal' | 'square') => {
        // Validar tamaño (máx 5MB)
        if (file.size > 5 * 1024 * 1024) {
            showToast('El archivo no puede superar 5MB', 'error');
            return;
        }

        // Validar tipo
        if (!file.type.startsWith('image/')) {
            showToast('Solo se permiten imágenes', 'error');
            return;
        }

        try {
            await uploadLogo.mutateAsync({ file, type });
            showToast(`Logo ${type === 'horizontal' ? 'horizontal' : 'cuadrado'} actualizado`, 'success');

            // Limpiar preview
            if (type === 'horizontal') {
                setHorizontalPreview(null);
            } else {
                setSquarePreview(null);
            }
        } catch (error) {
            showToast('Error al subir el logo', 'error');
            console.error(error);
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, type: 'horizontal' | 'square') => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Crear preview
        const reader = new FileReader();
        reader.onloadend = () => {
            if (type === 'horizontal') {
                setHorizontalPreview(reader.result as string);
            } else {
                setSquarePreview(reader.result as string);
            }
        };
        reader.readAsDataURL(file);

        // Subir automáticamente
        handleLogoUpload(file, type);
    };

    if (brandingQuery.isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-sm text-slate-500">Cargando...</div>
            </div>
        );
    }

    if (brandingQuery.isError) {
        return (
            <div className="rounded-lg bg-red-50 p-4">
                <p className="text-sm text-red-800">Error al cargar el branding. Intentá nuevamente.</p>
            </div>
        );
    }

    const horizontalLogoUrl = horizontalPreview || brandingQuery.data?.logo_horizontal_url;
    const squareLogoUrl = squarePreview || brandingQuery.data?.logo_square_url;

    return (
        <>
            <div className="space-y-6">
                {/* Logos */}
                <Card className="p-6">
                    <div className="mb-6">
                        <h2 className="text-xl font-semibold text-slate-900">Logos</h2>
                        <p className="mt-1 text-sm text-slate-600">
                            Subí los logos de tu negocio para usar en PDFs, menú online y más.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                        {/* Logo Horizontal */}
                        <div className="space-y-4">
                            <div>
                                <h3 className="text-sm font-medium text-slate-900">Logo Horizontal</h3>
                                <p className="text-xs text-slate-500">Para facturas y presupuestos (recomendado: 400x100px)</p>
                            </div>

                            {horizontalLogoUrl && (
                                <div className="relative h-24 w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                                    <Image
                                        src={horizontalLogoUrl}
                                        alt="Logo horizontal"
                                        fill
                                        className="object-contain p-2"
                                    />
                                </div>
                            )}

                            <div>
                                <label
                                    htmlFor="logo_horizontal"
                                    className={cn(
                                        'inline-flex cursor-pointer items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50',
                                        uploadLogo.isPending && 'cursor-not-allowed opacity-50'
                                    )}
                                >
                                    {uploadLogo.isPending ? 'Subiendo...' : horizontalLogoUrl ? 'Cambiar Logo' : 'Subir Logo'}
                                </label>
                                <input
                                    type="file"
                                    id="logo_horizontal"
                                    accept="image/*"
                                    onChange={(e) => handleFileChange(e, 'horizontal')}
                                    className="hidden"
                                    disabled={uploadLogo.isPending}
                                />
                            </div>
                        </div>

                        {/* Logo Cuadrado */}
                        <div className="space-y-4">
                            <div>
                                <h3 className="text-sm font-medium text-slate-900">Logo Cuadrado</h3>
                                <p className="text-xs text-slate-500">Para menú QR y apps (recomendado: 400x400px)</p>
                            </div>

                            {squareLogoUrl && (
                                <div className="relative h-24 w-24 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                                    <Image src={squareLogoUrl} alt="Logo cuadrado" fill className="object-contain p-2" />
                                </div>
                            )}

                            <div>
                                <label
                                    htmlFor="logo_square"
                                    className={cn(
                                        'inline-flex cursor-pointer items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50',
                                        uploadLogo.isPending && 'cursor-not-allowed opacity-50'
                                    )}
                                >
                                    {uploadLogo.isPending ? 'Subiendo...' : squareLogoUrl ? 'Cambiar Logo' : 'Subir Logo'}
                                </label>
                                <input
                                    type="file"
                                    id="logo_square"
                                    accept="image/*"
                                    onChange={(e) => handleFileChange(e, 'square')}
                                    className="hidden"
                                    disabled={uploadLogo.isPending}
                                />
                            </div>
                        </div>
                    </div>
                </Card>

                {/* Color Corporativo */}
                <Card className="p-6">
                    <div className="mb-6">
                        <h2 className="text-xl font-semibold text-slate-900">Color Corporativo</h2>
                        <p className="mt-1 text-sm text-slate-600">
                            Seleccioná el color principal de tu marca para personalizar documentos y menú online.
                        </p>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-3">
                                <input
                                    type="color"
                                    id="accent_color"
                                    value={accentColor}
                                    onChange={(e) => setAccentColor(e.target.value)}
                                    className="h-12 w-12 cursor-pointer rounded-md border border-slate-300"
                                />
                                <div>
                                    <label htmlFor="accent_color" className="block text-sm font-medium text-slate-700">
                                        Color Hex
                                    </label>
                                    <input
                                        type="text"
                                        value={accentColor}
                                        onChange={(e) => setAccentColor(e.target.value)}
                                        pattern="^#[0-9A-Fa-f]{6}$"
                                        placeholder="#000000"
                                        className="mt-1 block w-32 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                    />
                                </div>
                            </div>

                            <button
                                type="button"
                                onClick={handleColorChange}
                                disabled={updateBranding.isPending}
                                className={cn(
                                    'rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
                                    updateBranding.isPending && 'cursor-not-allowed opacity-50'
                                )}
                            >
                                {updateBranding.isPending ? 'Guardando...' : 'Guardar Color'}
                            </button>
                        </div>

                        {/* Preview */}
                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                            <p className="mb-3 text-xs font-medium text-slate-700">Vista Previa:</p>
                            <div className="flex gap-3">
                                <div
                                    className="h-12 w-12 rounded-md border border-slate-300"
                                    style={{ backgroundColor: accentColor }}
                                />
                                <div>
                                    <p className="text-sm font-medium" style={{ color: accentColor }}>
                                        Texto con color corporativo
                                    </p>
                                    <button
                                        type="button"
                                        className="mt-1 rounded-md px-3 py-1 text-xs font-medium text-white"
                                        style={{ backgroundColor: accentColor }}
                                    >
                                        Botón de ejemplo
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </Card>
            </div>

            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </>
    );
}
