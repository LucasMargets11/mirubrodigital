'use client';

import { useEffect, useRef, useState } from 'react';

import { Card } from '@/components/ui/card';
import { Modal } from '@/components/ui/modal';
import { Badge } from '@/components/ui/badge';
import { ToastBubble } from '@/components/app/toast';
import {
    useDocumentSeriesQuery,
    useCreateDocumentSeriesMutation,
    useUpdateDocumentSeriesMutation,
    useSetDocumentSeriesDefaultMutation,
} from '@/features/gestion/hooks';
import type { DocumentSeries, DocumentSeriesPayload, DocumentType, DocumentLetter } from '@/features/gestion/types';
import { cn } from '@/lib/utils';

type ToastState = { message: string; tone: 'success' | 'error' };

const DOCUMENT_TYPE_OPTIONS: { value: DocumentType; label: string }[] = [
    { value: 'invoice', label: 'Factura' },
    { value: 'quote', label: 'Presupuesto' },
    { value: 'receipt', label: 'Recibo' },
    { value: 'credit_note', label: 'Nota de Crédito' },
    { value: 'debit_note', label: 'Nota de Débito' },
    { value: 'delivery_note', label: 'Remito' },
];

const LETTER_OPTIONS: { value: DocumentLetter; label: string }[] = [
    { value: 'A', label: 'A' },
    { value: 'B', label: 'B' },
    { value: 'C', label: 'C' },
    { value: 'E', label: 'E' },
    { value: 'M', label: 'M' },
    { value: 'X', label: 'X' },
    { value: 'P', label: 'P (Presupuestos)' },
];

export function DocumentSeriesTab() {
    const seriesQuery = useDocumentSeriesQuery();
    const createSeries = useCreateDocumentSeriesMutation();
    const updateSeries = useUpdateDocumentSeriesMutation();
    const setDefault = useSetDocumentSeriesDefaultMutation();
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingSeries, setEditingSeries] = useState<DocumentSeries | null>(null);
    const [filterType, setFilterType] = useState<DocumentType | 'all'>('all');

    const [formData, setFormData] = useState<DocumentSeriesPayload>({
        document_type: 'invoice',
        letter: 'X',
        prefix: '',
        suffix: '',
        point_of_sale: 1,
        is_active: true,
        is_default: false,
    });

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

    const handleOpenModal = (series?: DocumentSeries) => {
        if (series) {
            setEditingSeries(series);
            setFormData({
                document_type: series.document_type,
                letter: series.letter,
                prefix: series.prefix,
                suffix: series.suffix,
                point_of_sale: series.point_of_sale,
                is_active: series.is_active,
                is_default: series.is_default,
            });
        } else {
            setEditingSeries(null);
            setFormData({
                document_type: 'invoice',
                letter: 'X',
                prefix: '',
                suffix: '',
                point_of_sale: 1,
                is_active: true,
                is_default: false,
            });
        }
        setIsModalOpen(true);
    };

    const handleCloseModal = () => {
        setIsModalOpen(false);
        setEditingSeries(null);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        try {
            if (editingSeries) {
                await updateSeries.mutateAsync({ seriesId: editingSeries.id, payload: formData });
                showToast('Serie actualizada correctamente', 'success');
            } else {
                await createSeries.mutateAsync(formData);
                showToast('Serie creada correctamente', 'success');
            }
            handleCloseModal();
        } catch (error: any) {
            const errorMessage = error?.detail || 'Error al guardar la serie';
            showToast(errorMessage, 'error');
            console.error(error);
        }
    };

    const handleSetDefault = async (seriesId: string) => {
        try {
            await setDefault.mutateAsync(seriesId);
            showToast('Serie establecida como predeterminada', 'success');
        } catch (error) {
            showToast('Error al establecer como predeterminada', 'error');
            console.error(error);
        }
    };

    const handleToggleActive = async (series: DocumentSeries) => {
        try {
            await updateSeries.mutateAsync({
                seriesId: series.id,
                payload: { is_active: !series.is_active },
            });
            showToast(series.is_active ? 'Serie desactivada' : 'Serie activada', 'success');
        } catch (error) {
            showToast('Error al cambiar estado', 'error');
            console.error(error);
        }
    };

    if (seriesQuery.isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-sm text-slate-500">Cargando...</div>
            </div>
        );
    }

    if (seriesQuery.isError) {
        return (
            <div className="rounded-lg bg-red-50 p-4">
                <p className="text-sm text-red-800">Error al cargar las series. Intentá nuevamente.</p>
            </div>
        );
    }

    const allSeries = seriesQuery.data || [];
    const filteredSeries = filterType === 'all' ? allSeries : allSeries.filter((s) => s.document_type === filterType);

    return (
        <>
            <Card className="p-6">
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-semibold text-slate-900">Series de Documentos</h2>
                        <p className="mt-1 text-sm text-slate-600">
                            Gestioná las series de numeración para facturas, presupuestos y otros documentos.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={() => handleOpenModal()}
                        className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
                    >
                        Nueva Serie
                    </button>
                </div>

                {/* Filtros */}
                <div className="mb-4 flex gap-2">
                    <button
                        type="button"
                        onClick={() => setFilterType('all')}
                        className={cn(
                            'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                            filterType === 'all'
                                ? 'bg-brand-100 text-brand-700'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        )}
                    >
                        Todas
                    </button>
                    {DOCUMENT_TYPE_OPTIONS.map((option) => (
                        <button
                            key={option.value}
                            type="button"
                            onClick={() => setFilterType(option.value)}
                            className={cn(
                                'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                                filterType === option.value
                                    ? 'bg-brand-100 text-brand-700'
                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            )}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>

                {/* Tabla */}
                <div className="overflow-hidden rounded-lg border border-slate-200">
                    <table className="min-w-full divide-y divide-slate-200">
                        <thead className="bg-slate-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Tipo
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Letra
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Prefijo
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Pto. Venta
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Próximo Nº
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Estado
                                </th>
                                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-slate-700">
                                    Acciones
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 bg-white">
                            {filteredSeries.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500">
                                        No hay series configuradas. Creá una para comenzar.
                                    </td>
                                </tr>
                            ) : (
                                filteredSeries.map((series) => (
                                    <tr key={series.id} className="hover:bg-slate-50">
                                        <td className="px-4 py-3 text-sm">
                                            <div className="flex items-center gap-2">
                                                {series.document_type_display}
                                                {series.is_default && (
                                                    <Badge className="bg-blue-100 text-blue-700">Default</Badge>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-sm font-medium text-slate-900">{series.letter}</td>
                                        <td className="px-4 py-3 text-sm text-slate-600">{series.prefix || '—'}</td>
                                        <td className="px-4 py-3 text-sm text-slate-600">
                                            {String(series.point_of_sale).padStart(4, '0')}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-600">
                                            {String(series.next_number).padStart(8, '0')}
                                        </td>
                                        <td className="px-4 py-3 text-sm">
                                            {series.is_active ? (
                                                <Badge className="bg-green-100 text-green-700">Activa</Badge>
                                            ) : (
                                                <Badge className="bg-slate-100 text-slate-600">Inactiva</Badge>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-right text-sm">
                                            <div className="flex justify-end gap-2">
                                                {!series.is_default && (
                                                    <button
                                                        type="button"
                                                        onClick={() => handleSetDefault(series.id)}
                                                        className="text-xs text-blue-600 hover:text-blue-700 hover:underline"
                                                        disabled={setDefault.isPending}
                                                    >
                                                        Establecer Default
                                                    </button>
                                                )}
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleActive(series)}
                                                    className="text-xs text-slate-600 hover:text-slate-700 hover:underline"
                                                    disabled={updateSeries.isPending}
                                                >
                                                    {series.is_active ? 'Desactivar' : 'Activar'}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => handleOpenModal(series)}
                                                    className="text-xs text-brand-600 hover:text-brand-700 hover:underline"
                                                >
                                                    Editar
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {allSeries.length > 0 && (
                    <div className="mt-4 text-xs text-slate-500">
                        Mostrando {filteredSeries.length} de {allSeries.length} series
                    </div>
                )}
            </Card>

            {/* Modal Crear/Editar */}
            <Modal open={isModalOpen} onClose={handleCloseModal} title={editingSeries ? 'Editar Serie' : 'Nueva Serie'}>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <div>
                            <label htmlFor="document_type" className="block text-sm font-medium text-slate-700">
                                Tipo de Documento <span className="text-red-500">*</span>
                            </label>
                            <select
                                id="document_type"
                                value={formData.document_type}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, document_type: e.target.value as DocumentType }))
                                }
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                required
                                disabled={!!editingSeries}
                            >
                                {DOCUMENT_TYPE_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div>
                            <label htmlFor="letter" className="block text-sm font-medium text-slate-700">
                                Letra <span className="text-red-500">*</span>
                            </label>
                            <select
                                id="letter"
                                value={formData.letter}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, letter: e.target.value as DocumentLetter }))
                                }
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                required
                                disabled={!!editingSeries}
                            >
                                {LETTER_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div>
                            <label htmlFor="prefix" className="block text-sm font-medium text-slate-700">
                                Prefijo (opcional)
                            </label>
                            <input
                                type="text"
                                id="prefix"
                                value={formData.prefix}
                                onChange={(e) => setFormData((prev) => ({ ...prev, prefix: e.target.value }))}
                                placeholder="FAC, PRE, etc."
                                maxLength={10}
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                            />
                        </div>

                        <div>
                            <label htmlFor="point_of_sale" className="block text-sm font-medium text-slate-700">
                                Punto de Venta <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="number"
                                id="point_of_sale"
                                value={formData.point_of_sale}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, point_of_sale: parseInt(e.target.value, 10) }))
                                }
                                min={1}
                                max={9999}
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                required
                                disabled={!!editingSeries}
                            />
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        <label className="flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={formData.is_active}
                                onChange={(e) => setFormData((prev) => ({ ...prev, is_active: e.target.checked }))}
                                className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                            />
                            <span className="text-sm text-slate-700">Activa</span>
                        </label>

                        <label className="flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={formData.is_default}
                                onChange={(e) => setFormData((prev) => ({ ...prev, is_default: e.target.checked }))}
                                className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                            />
                            <span className="text-sm text-slate-700">Predeterminada</span>
                        </label>
                    </div>

                    {!editingSeries && (
                        <div className="rounded-md bg-blue-50 p-3">
                            <p className="text-xs text-blue-800">
                                💡 No podés editar el tipo, letra o punto de venta después de crear la serie.
                            </p>
                        </div>
                    )}

                    <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
                        <button
                            type="button"
                            onClick={handleCloseModal}
                            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            disabled={createSeries.isPending || updateSeries.isPending}
                            className={cn(
                                'rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
                                (createSeries.isPending || updateSeries.isPending) && 'cursor-not-allowed opacity-50'
                            )}
                        >
                            {createSeries.isPending || updateSeries.isPending
                                ? 'Guardando...'
                                : editingSeries
                                  ? 'Actualizar'
                                  : 'Crear Serie'}
                        </button>
                    </div>
                </form>
            </Modal>

            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </>
    );
}
