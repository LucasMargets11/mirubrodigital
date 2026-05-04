'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useSubmitFirstProduct, useSkipOnboardingStep } from '@/features/onboarding/gestion/hooks';
import type { GestionOnboardingContext } from '@/features/onboarding/gestion/types';

interface Props {
    context: GestionOnboardingContext;
    onComplete: () => void;
    onSkip: () => void;
    onBack: () => void;
}

export function FirstProductStep({ context, onComplete, onSkip, onBack }: Props) {
    const submitMutation = useSubmitFirstProduct();
    const skipMutation = useSkipOnboardingStep();

    const [name, setName] = useState('');
    const [price, setPrice] = useState('');
    const [cost, setCost] = useState('');
    const [categoryName, setCategoryName] = useState('');
    const [initialStock, setInitialStock] = useState('');
    const [error, setError] = useState<string | null>(null);

    const hasInventory = context.features.inventory_basic;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const trimmedName = name.trim();
        if (trimmedName.length < 2) {
            setError('El nombre del producto debe tener al menos 2 caracteres.');
            return;
        }

        const parsedPrice = parseFloat(price);
        if (!price || isNaN(parsedPrice) || parsedPrice < 0) {
            setError('Ingresá un precio válido (mayor o igual a 0).');
            return;
        }

        const parsedCost = cost ? parseFloat(cost) : null;
        if (cost && (isNaN(parsedCost!) || parsedCost! < 0)) {
            setError('El costo debe ser mayor o igual a 0.');
            return;
        }

        const parsedStock = initialStock ? parseFloat(initialStock) : null;
        if (initialStock && (isNaN(parsedStock!) || parsedStock! < 0)) {
            setError('El stock inicial debe ser mayor o igual a 0.');
            return;
        }

        try {
            await submitMutation.mutateAsync({
                name: trimmedName,
                price: parsedPrice.toString(),
                cost: parsedCost !== null ? parsedCost.toString() : null,
                category_name: categoryName.trim() || null,
                initial_stock: parsedStock !== null ? parsedStock.toString() : null,
            });
            onComplete();
        } catch {
            setError('No se pudo crear el producto. Intentá nuevamente.');
        }
    };

    const handleSkip = async () => {
        try {
            await skipMutation.mutateAsync({ step_id: 'first_product' });
        } catch {
            // non-fatal
        }
        onSkip();
    };

    const isSubmitting = submitMutation.isPending;
    const isSkipping = skipMutation.isPending;

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {/* Step header */}
            <div className="space-y-1">
                <h2 className="text-lg font-semibold text-slate-900">
                    Cargá tu primer producto o servicio
                </h2>
                <p className="text-sm text-slate-500">
                    Agregá uno como prueba. Después podés cargar el catálogo completo desde Productos con todos los detalles.
                </p>
            </div>

            {/* Fields */}
            <div className="space-y-4">
                <div className="space-y-1.5">
                    <label htmlFor="product-name" className="block text-sm font-medium text-slate-700">
                        Nombre del producto o servicio <span className="text-red-500">*</span>
                    </label>
                    <input
                        id="product-name"
                        type="text"
                        autoFocus
                        placeholder="Ej: Café con leche"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                        <label htmlFor="product-price" className="block text-sm font-medium text-slate-700">
                            Precio de venta <span className="text-red-500">*</span>
                        </label>
                        <div className="relative">
                            <span className="absolute inset-y-0 left-3 flex items-center text-sm text-slate-400">$</span>
                            <input
                                id="product-price"
                                type="number"
                                min="0"
                                step="0.01"
                                placeholder="0.00"
                                value={price}
                                onChange={(e) => setPrice(e.target.value)}
                                className="w-full rounded-md border border-slate-300 py-2 pl-7 pr-3 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                    </div>

                    <div className="space-y-1.5">
                        <label htmlFor="product-cost" className="block text-sm font-medium text-slate-700">
                            Costo <span className="text-slate-400 font-normal">(opcional)</span>
                        </label>
                        <div className="relative">
                            <span className="absolute inset-y-0 left-3 flex items-center text-sm text-slate-400">$</span>
                            <input
                                id="product-cost"
                                type="number"
                                min="0"
                                step="0.01"
                                placeholder="0.00"
                                value={cost}
                                onChange={(e) => setCost(e.target.value)}
                                className="w-full rounded-md border border-slate-300 py-2 pl-7 pr-3 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                    </div>
                </div>

                <div className="space-y-1.5">
                    <label htmlFor="category-name" className="block text-sm font-medium text-slate-700">
                        Categoría <span className="text-slate-400 font-normal">(opcional)</span>
                    </label>
                    <input
                        id="category-name"
                        type="text"
                        placeholder="Ej: Bebidas"
                        value={categoryName}
                        onChange={(e) => setCategoryName(e.target.value)}
                        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                </div>

                {hasInventory && (
                    <div className="space-y-1.5">
                        <label htmlFor="initial-stock" className="block text-sm font-medium text-slate-700">
                            Stock inicial <span className="text-slate-400 font-normal">(opcional)</span>
                        </label>
                        <input
                            id="initial-stock"
                            type="number"
                            min="0"
                            step="1"
                            placeholder="0"
                            value={initialStock}
                            onChange={(e) => setInitialStock(e.target.value)}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                        <p className="text-xs text-slate-400">Cantidad que tenés disponible ahora. Se registra como ingreso de stock.</p>
                    </div>
                )}
            </div>

            {/* Error */}
            {error && (
                <p className="text-sm text-red-600">{error}</p>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <button
                        type="button"
                        onClick={onBack}
                        disabled={isSubmitting || isSkipping}
                        className="text-sm text-slate-400 hover:text-slate-600 disabled:opacity-50"
                    >
                        ← Volver
                    </button>
                    <button
                        type="button"
                        onClick={handleSkip}
                        disabled={isSkipping || isSubmitting}
                        className="text-sm text-slate-400 hover:text-slate-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {isSkipping ? 'Saltando...' : 'Saltar este paso'}
                    </button>
                </div>

                <Button type="submit" disabled={isSubmitting || isSkipping}>
                    {isSubmitting ? 'Creando producto...' : 'Crear y continuar'}
                </Button>
            </div>
        </form>
    );
}
