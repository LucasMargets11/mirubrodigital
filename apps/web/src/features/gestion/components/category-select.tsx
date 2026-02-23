'use client';

import { useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { useProductCategories, useCreateProductCategory } from '../hooks';
import type { ProductCategorySummary } from '../types';

interface CategorySelectProps {
    value: string | null | undefined;
    onChange: (value: string | null) => void;
    disabled?: boolean;
    error?: string;
}

export function CategorySelect({ value, onChange, disabled, error }: CategorySelectProps) {
    const [search, setSearch] = useState('');
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newCategoryName, setNewCategoryName] = useState('');
    const [createError, setCreateError] = useState('');

    const { data: categories = [], isLoading } = useProductCategories(search);
    const createCategory = useCreateProductCategory();

    // Filter categories based on search
    const filteredCategories = useMemo(() => {
        if (!search.trim()) return categories;
        const searchLower = search.toLowerCase();
        return categories.filter((cat) => cat.name.toLowerCase().includes(searchLower));
    }, [categories, search]);

    const selectedCategory = categories.find((cat) => cat.id === value);

    const handleCreateCategory = async () => {
        const trimmedName = newCategoryName.trim();
        
        if (trimmedName.length < 2) {
            setCreateError('El nombre debe tener al menos 2 caracteres.');
            return;
        }

        if (trimmedName.length > 100) {
            setCreateError('El nombre no puede exceder 100 caracteres.');
            return;
        }

        try {
            const newCategory = await createCategory.mutateAsync({ name: trimmedName });
            onChange(newCategory.id);
            setShowCreateModal(false);
            setNewCategoryName('');
            setCreateError('');
        } catch (err: any) {
            if (err.payload?.name) {
                setCreateError(err.payload.name[0] || 'Ya existe una categoría con este nombre.');
            } else {
                setCreateError('Error al crear la categoría. Intente nuevamente.');
            }
        }
    };

    const handleQuickCreate = () => {
        setNewCategoryName(search);
        setShowCreateModal(true);
    };

    return (
        <div className="space-y-2">
            <label htmlFor="category-select" className="block text-sm font-medium">
                Categoría
            </label>
            <p id="category-help" className="text-sm text-gray-600 dark:text-gray-400">
                Opcional. Úsenlo para organizar y filtrar productos.
            </p>

            <div className="flex gap-2">
                <div className="flex-1">
                    <select
                        id="category-select"
                        value={value || ''}
                        onChange={(e) => onChange(e.target.value || null)}
                        disabled={disabled || isLoading}
                        aria-describedby="category-help"
                        aria-invalid={!!error}
                        className={`w-full rounded-xl border px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:opacity-50 ${
                            error ? 'border-red-500' : 'border-slate-200'
                        }`}
                    >
                        <option value="">Sin categoría</option>
                        {filteredCategories.map((category) => (
                            <option key={category.id} value={category.id}>
                                {category.name}
                            </option>
                        ))}
                    </select>
                </div>

                <Button
                    type="button"
                    onClick={() => setShowCreateModal(true)}
                    disabled={disabled || isLoading}
                    variant="outline"
                    aria-label="Crear nueva categoría"
                >
                    + Nueva
                </Button>
            </div>

            {error && (
                <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                    {error}
                </p>
            )}

            <Modal
                open={showCreateModal}
                onClose={() => {
                    setShowCreateModal(false);
                    setNewCategoryName('');
                    setCreateError('');
                }}
                title="Crear categoría"
            >
                <div className="space-y-4">
                    <div>
                        <label htmlFor="new-category-name" className="block text-sm font-medium mb-2">
                            Nombre de la categoría
                        </label>
                        <input
                            id="new-category-name"
                            type="text"
                            value={newCategoryName}
                            onChange={(e) => {
                                setNewCategoryName(e.target.value);
                                setCreateError('');
                            }}
                            placeholder="Ej: Bebidas, Alimentos, Electrónica..."
                            maxLength={100}
                            className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                                createError ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                            } bg-white dark:bg-gray-800`}
                            autoFocus
                        />
                        {createError && (
                            <p className="text-sm text-red-600 dark:text-red-400 mt-1" role="alert">
                                {createError}
                            </p>
                        )}
                    </div>

                    <div className="flex gap-3 justify-end">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => {
                                setShowCreateModal(false);
                                setNewCategoryName('');
                                setCreateError('');
                            }}
                            disabled={createCategory.isPending}
                        >
                            Cancelar
                        </Button>
                        <Button
                            type="button"
                            onClick={handleCreateCategory}
                            disabled={createCategory.isPending || !newCategoryName.trim()}
                        >
                            {createCategory.isPending ? 'Creando...' : 'Crear'}
                        </Button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
