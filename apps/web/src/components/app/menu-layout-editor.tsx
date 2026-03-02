'use client';

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { ToastBubble } from '@/components/app/toast';
import {
    listMenuLayoutBlocks,
    createMenuLayoutBlock,
    updateMenuLayoutBlock,
    deleteMenuLayoutBlock,
    reorderMenuLayoutBlocks,
    applyMenuLayoutPreset,
    listMenuCategories,
} from '@/features/menu/api';
import type { MenuLayoutBlock, MenuLayoutBlockPayload, MenuCategory } from '@/features/menu/types';

// ─── Small helpers ─────────────────────────────────────────────────────────────

function Badge({ children, className = '' }: { children: React.ReactNode; className?: string }) {
    return (
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${className}`}>
            {children}
        </span>
    );
}

// ─── Block editor modal (inline, not a real modal to avoid extra deps) ─────────

interface BlockFormProps {
    block: Partial<MenuLayoutBlock>;
    allCategories: MenuCategory[];
    assignedCategoryIds: Set<string>; // IDs already used by OTHER blocks
    onSave: (data: MenuLayoutBlockPayload) => Promise<void>;
    onCancel: () => void;
}

function BlockForm({ block, allCategories, assignedCategoryIds, onSave, onCancel }: BlockFormProps) {
    const [title, setTitle] = useState(block.title ?? '');
    const [layout, setLayout] = useState<'stack' | 'grid'>(block.layout ?? 'stack');
    const [colsDesktop, setColsDesktop] = useState(block.columns_desktop ?? 3);
    const [colsTablet, setColsTablet] = useState(block.columns_tablet ?? 2);
    const [badgeText, setBadgeText] = useState(block.badge_text ?? '');
    const [saving, setSaving] = useState(false);

    // Selected category IDs in order
    const initialCatIds = (block.block_categories ?? []).map((bc) => bc.category_id);
    const [selectedIds, setSelectedIds] = useState<string[]>(initialCatIds);

    const availableCategories = allCategories.filter(
        (c) => !assignedCategoryIds.has(c.id) || selectedIds.includes(c.id)
    );

    function toggleCategory(id: string) {
        setSelectedIds((prev) =>
            prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
        );
    }

    function moveCat(id: string, dir: -1 | 1) {
        setSelectedIds((prev) => {
            const idx = prev.indexOf(id);
            if (idx < 0) return prev;
            const next = [...prev];
            const swap = idx + dir;
            if (swap < 0 || swap >= next.length) return prev;
            [next[idx], next[swap]] = [next[swap], next[idx]];
            return next;
        });
    }

    async function handleSave() {
        if (!title.trim()) return;
        setSaving(true);
        try {
            await onSave({
                title: title.trim(),
                layout,
                columns_desktop: colsDesktop,
                columns_tablet: colsTablet,
                columns_mobile: 1,
                badge_text: badgeText.trim(),
                position: block.position ?? 0,
                category_ids: selectedIds,
            });
        } finally {
            setSaving(false);
        }
    }

    const selectedCats = selectedIds
        .map((id) => allCategories.find((c) => c.id === id))
        .filter(Boolean) as MenuCategory[];

    return (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <h3 className="font-semibold text-slate-800">
                {block.id ? 'Editar bloque' : 'Nuevo bloque'}
            </h3>

            {/* Title */}
            <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Nombre del bloque *</label>
                <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="ej: Bebidas, Comida, Postres…"
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
            </div>

            {/* Badge */}
            <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                    Badge / Etiqueta (opcional)
                </label>
                <input
                    value={badgeText}
                    onChange={(e) => setBadgeText(e.target.value)}
                    placeholder="ej: Happy Hour · Hasta 20 hs"
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
            </div>

            {/* Layout */}
            <div>
                <label className="block text-xs font-medium text-slate-600 mb-2">Tipo de vista</label>
                <div className="flex gap-2">
                    {(['stack', 'grid'] as const).map((l) => (
                        <button
                            key={l}
                            onClick={() => setLayout(l)}
                            className={`flex-1 rounded-md border px-3 py-2 text-xs transition-colors ${
                                layout === l
                                    ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium ring-1 ring-blue-500'
                                    : 'border-slate-200 hover:border-slate-300'
                            }`}
                        >
                            {l === 'stack' ? '☰ Lista' : '⊞ Cuadrícula'}
                        </button>
                    ))}
                </div>
            </div>

            {/* Columns */}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                        Columnas desktop
                    </label>
                    <select
                        value={colsDesktop}
                        onChange={(e) => setColsDesktop(Number(e.target.value))}
                        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                    >
                        {[1, 2, 3, 4].map((n) => (
                            <option key={n} value={n}>{n} col.</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                        Columnas tablet
                    </label>
                    <select
                        value={colsTablet}
                        onChange={(e) => setColsTablet(Number(e.target.value))}
                        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                    >
                        {[1, 2, 3].map((n) => (
                            <option key={n} value={n}>{n} col.</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Category assignment */}
            <div>
                <label className="block text-xs font-medium text-slate-600 mb-2">
                    Categorías asignadas ({selectedIds.length})
                </label>

                {/* Selected — ordered list */}
                {selectedCats.length > 0 && (
                    <div className="mb-3 space-y-1 rounded-lg border border-slate-200 bg-slate-50 p-2">
                        {selectedCats.map((cat, idx) => (
                            <div
                                key={cat.id}
                                className="flex items-center justify-between gap-2 rounded-md bg-white px-2 py-1 shadow-sm"
                            >
                                <span className="min-w-0 truncate text-xs font-medium">{cat.name}</span>
                                <div className="flex shrink-0 items-center gap-1">
                                    <button
                                        onClick={() => moveCat(cat.id, -1)}
                                        disabled={idx === 0}
                                        className="rounded p-0.5 text-slate-400 hover:bg-slate-100 disabled:opacity-30"
                                        title="Mover arriba"
                                    >↑</button>
                                    <button
                                        onClick={() => moveCat(cat.id, 1)}
                                        disabled={idx === selectedCats.length - 1}
                                        className="rounded p-0.5 text-slate-400 hover:bg-slate-100 disabled:opacity-30"
                                        title="Mover abajo"
                                    >↓</button>
                                    <button
                                        onClick={() => toggleCategory(cat.id)}
                                        className="rounded p-0.5 text-rose-400 hover:bg-rose-50"
                                        title="Quitar"
                                    >✕</button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Available to add */}
                <div className="flex flex-wrap gap-1.5">
                    {availableCategories
                        .filter((c) => !selectedIds.includes(c.id))
                        .map((cat) => (
                            <button
                                key={cat.id}
                                onClick={() => toggleCategory(cat.id)}
                                className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                            >
                                + {cat.name}
                            </button>
                        ))}
                    {availableCategories.filter((c) => !selectedIds.includes(c.id)).length === 0 &&
                        selectedIds.length === 0 && (
                            <p className="text-xs text-slate-400">
                                No hay categorías disponibles. Crea categorías en la sección Carta primero.
                            </p>
                        )}
                </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>
                    Cancelar
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving || !title.trim()}>
                    {saving ? 'Guardando…' : 'Guardar bloque'}
                </Button>
            </div>
        </div>
    );
}

// ─── Main component ────────────────────────────────────────────────────────────

export function MenuLayoutEditor() {
    const [blocks, setBlocks] = useState<MenuLayoutBlock[]>([]);
    const [categories, setCategories] = useState<MenuCategory[]>([]);
    const [loading, setLoading] = useState(true);
    const [editingBlock, setEditingBlock] = useState<MenuLayoutBlock | null | 'new'>(null);
    const [toast, setToast] = useState<{ message: string; tone: 'success' | 'error' | 'info' } | null>(null);
    const [applying, setApplying] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

    const showToast = useCallback(
        (message: string, tone: 'success' | 'error' | 'info' = 'success') => {
            setToast({ message, tone });
            setTimeout(() => setToast(null), 3500);
        },
        []
    );

    useEffect(() => {
        Promise.all([listMenuLayoutBlocks(), listMenuCategories()])
            .then(([blks, cats]) => {
                setBlocks(blks);
                setCategories(cats);
            })
            .catch(() => showToast('Error cargando datos', 'error'))
            .finally(() => setLoading(false));
    }, []);

    // IDs already assigned in OTHER blocks (for exclusivity enforcement in form)
    function assignedIdsExcluding(excludeBlockId: string | undefined) {
        const used = new Set<string>();
        blocks.forEach((b) => {
            if (b.id === excludeBlockId) return;
            b.block_categories.forEach((bc) => used.add(bc.category_id));
        });
        return used;
    }

    async function handleSaveBlock(payload: MenuLayoutBlockPayload) {
        try {
            if (editingBlock === 'new') {
                const positionForNew = blocks.length;
                const newBlock = await createMenuLayoutBlock({ ...payload, position: positionForNew });
                setBlocks((prev) => [...prev, newBlock]);
                showToast('Bloque creado');
            } else if (editingBlock) {
                const updated = await updateMenuLayoutBlock(editingBlock.id, payload);
                setBlocks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
                showToast('Bloque actualizado');
            }
            setEditingBlock(null);
        } catch {
            showToast('Error al guardar el bloque', 'error');
            throw new Error('save failed');
        }
    }

    async function handleDeleteBlock(id: string) {
        try {
            await deleteMenuLayoutBlock(id);
            setBlocks((prev) => prev.filter((b) => b.id !== id));
            showToast('Bloque eliminado', 'info');
        } catch {
            showToast('Error al eliminar', 'error');
        } finally {
            setConfirmDelete(null);
        }
    }

    async function moveBlock(id: string, dir: -1 | 1) {
        const sorted = [...blocks].sort((a, b) => a.position - b.position);
        const idx = sorted.findIndex((b) => b.id === id);
        if (idx < 0) return;
        const swap = idx + dir;
        if (swap < 0 || swap >= sorted.length) return;

        [sorted[idx].position, sorted[swap].position] = [sorted[swap].position, sorted[idx].position];
        setBlocks([...sorted]); // optimistic

        try {
            await reorderMenuLayoutBlocks(
                sorted.map((b) => ({ id: b.id, position: b.position }))
            );
        } catch {
            showToast('Error al reordenar', 'error');
        }
    }

    async function handleApplyPreset(template: 'drinks_first' | 'food_first') {
        if (!confirm(`¿Aplicar el preset "${template === 'drinks_first' ? 'Bebidas primero' : 'Comida primero'}"? Se borrarán los bloques actuales y se asignarán las categorías por nombre.`)) return;
        setApplying(true);
        try {
            const newBlocks = await applyMenuLayoutPreset(template);
            setBlocks(newBlocks);
            showToast('Preset aplicado correctamente');
        } catch {
            showToast('Error aplicando preset', 'error');
        } finally {
            setApplying(false);
        }
    }

    if (loading) {
        return <div className="py-6 text-center text-sm text-slate-500">Cargando estructura…</div>;
    }

    const sorted = [...blocks].sort((a, b) => a.position - b.position);
    const isEditingExisting = editingBlock && editingBlock !== 'new';

    return (
        <div className="space-y-5">
            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}

            {/* Header + actions */}
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <p className="text-xs text-slate-500 max-w-lg">
                        Define el orden y agrupación de categorías en tu carta pública. Las
                        categorías vacías o inactivas no se muestran al cliente.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <span className="text-xs text-slate-500 self-center mr-1">Presets rápidos:</span>
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={applying}
                        onClick={() => handleApplyPreset('drinks_first')}
                    >
                        🍹 Bebidas primero
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={applying}
                        onClick={() => handleApplyPreset('food_first')}
                    >
                        🍽 Comida primero
                    </Button>
                    <Button
                        size="sm"
                        disabled={editingBlock !== null}
                        onClick={() => setEditingBlock('new')}
                    >
                        + Nuevo bloque
                    </Button>
                </div>
            </div>

            {/* New block form */}
            {editingBlock === 'new' && (
                <BlockForm
                    block={{ position: blocks.length }}
                    allCategories={categories}
                    assignedCategoryIds={assignedIdsExcluding(undefined)}
                    onSave={handleSaveBlock}
                    onCancel={() => setEditingBlock(null)}
                />
            )}

            {/* Empty state */}
            {sorted.length === 0 && editingBlock === null && (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center space-y-2">
                    <p className="text-sm font-medium text-slate-600">Sin bloques configurados</p>
                    <p className="text-xs text-slate-400">
                        Usá un preset para generar la estructura automáticamente, o creá bloques manualmente.
                    </p>
                    <p className="text-xs text-slate-400">
                        Sin bloques, la carta muestra las categorías en su orden original.
                    </p>
                </div>
            )}

            {/* Block list */}
            <div className="space-y-3">
                {sorted.map((block, idx) => {
                    const isEditing = isEditingExisting && editingBlock!.id === block.id;
                    const isDeleting = confirmDelete === block.id;
                    const catCount = block.block_categories.length;
                    const activeCount = block.block_categories.filter(
                        (bc) => bc.is_active
                    ).length;

                    if (isEditing) {
                        return (
                            <BlockForm
                                key={block.id}
                                block={block}
                                allCategories={categories}
                                assignedCategoryIds={assignedIdsExcluding(block.id)}
                                onSave={handleSaveBlock}
                                onCancel={() => setEditingBlock(null)}
                            />
                        );
                    }

                    return (
                        <div
                            key={block.id}
                            className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden"
                        >
                            <div className="flex items-center gap-3 px-4 py-3">
                                {/* Reorder */}
                                <div className="flex flex-col gap-0.5">
                                    <button
                                        onClick={() => moveBlock(block.id, -1)}
                                        disabled={idx === 0 || editingBlock !== null}
                                        className="rounded p-0.5 text-slate-400 hover:bg-slate-100 disabled:opacity-20 text-[10px] leading-none"
                                    >▲</button>
                                    <button
                                        onClick={() => moveBlock(block.id, 1)}
                                        disabled={idx === sorted.length - 1 || editingBlock !== null}
                                        className="rounded p-0.5 text-slate-400 hover:bg-slate-100 disabled:opacity-20 text-[10px] leading-none"
                                    >▼</button>
                                </div>

                                {/* Info */}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-semibold text-slate-800 text-sm">{block.title}</span>
                                        {block.badge_text && (
                                            <Badge className="bg-amber-100 text-amber-800">
                                                {block.badge_text}
                                            </Badge>
                                        )}
                                        <Badge className="bg-slate-100 text-slate-600">
                                            {block.layout === 'grid' ? '⊞ grid' : '☰ lista'}
                                        </Badge>
                                        <Badge className="bg-slate-100 text-slate-600">
                                            desktop {block.columns_desktop}col
                                        </Badge>
                                    </div>
                                    <div className="mt-1 flex flex-wrap gap-1">
                                        {block.block_categories.length === 0 ? (
                                            <span className="text-[11px] text-slate-400 italic">Sin categorías</span>
                                        ) : (
                                            block.block_categories
                                                .slice()
                                                .sort((a, b) => a.position - b.position)
                                                .map((bc) => (
                                                    <span
                                                        key={bc.category_id}
                                                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                                                            bc.is_active
                                                                ? 'bg-emerald-50 text-emerald-700'
                                                                : 'bg-slate-100 text-slate-400 line-through'
                                                        }`}
                                                    >
                                                        {bc.category_name}
                                                    </span>
                                                ))
                                        )}
                                    </div>
                                    {catCount > 0 && activeCount < catCount && (
                                        <p className="text-[10px] text-amber-600 mt-0.5">
                                            {catCount - activeCount} categoría(s) inactiva(s) — no se muestran en público
                                        </p>
                                    )}
                                </div>

                                {/* Actions */}
                                <div className="flex shrink-0 items-center gap-2">
                                    {isDeleting ? (
                                        <>
                                            <span className="text-xs text-rose-600 font-medium">¿Eliminar?</span>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="text-rose-600 border-rose-300 hover:bg-rose-50"
                                                onClick={() => handleDeleteBlock(block.id)}
                                            >
                                                Sí
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => setConfirmDelete(null)}
                                            >
                                                No
                                            </Button>
                                        </>
                                    ) : (
                                        <>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                disabled={editingBlock !== null}
                                                onClick={() => setEditingBlock(block)}
                                            >
                                                Editar
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="text-rose-500 border-rose-200 hover:bg-rose-50"
                                                disabled={editingBlock !== null}
                                                onClick={() => setConfirmDelete(block.id)}
                                            >
                                                Eliminar
                                            </Button>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
