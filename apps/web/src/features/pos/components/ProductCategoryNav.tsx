'use client';

/**
 * ProductCategoryNav
 *
 * Keyboard-navigable list of product categories for the POS terminal.
 *
 * Accessibility:
 * - Uses role="listbox" / role="option" so the whole nav is a singular
 *   widget with roving-tabindex arrow key navigation.
 * - The active option is marked aria-selected="true".
 * - Each option gets a visible focus ring.
 * - Category change is announced to screen readers by the parent via
 *   aria-live (the parent receives `onSelect` and manages the live region).
 */

import { useCallback, useEffect, useRef } from 'react';
import type { PosCategory } from '@/types/pos-cash';

interface ProductCategoryNavProps {
  categories: PosCategory[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  loading?: boolean;
  disabled?: boolean;
}

export function ProductCategoryNav({
  categories,
  selectedId,
  onSelect,
  loading = false,
  disabled = false,
}: ProductCategoryNavProps) {
  const listRef = useRef<HTMLUListElement>(null);

  // Build ordered list: "Todas" + real categories.
  const items: Array<{ id: string | null; label: string; count?: number }> = [
    { id: null, label: 'Todas' },
    ...categories.map((c) => ({
      id: c.id,
      label: c.name,
      count: c.products_count,
    })),
  ];

  const selectedIndex = items.findIndex((item) => item.id === selectedId);

  // Roving-tabindex: scroll focused item into view when it changes.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const focused = list.querySelector<HTMLElement>('[tabindex="0"]');
    focused?.scrollIntoView({ block: 'nearest' });
  }, [selectedId]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLUListElement>) => {
      if (disabled) return;

      const count = items.length;
      let nextIndex = selectedIndex;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        nextIndex = (selectedIndex + 1) % count;
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        nextIndex = (selectedIndex - 1 + count) % count;
      } else if (e.key === 'Home') {
        e.preventDefault();
        nextIndex = 0;
      } else if (e.key === 'End') {
        e.preventDefault();
        nextIndex = count - 1;
      } else {
        return;
      }

      onSelect(items[nextIndex].id);
      // Move DOM focus to the newly selected item.
      const listEl = listRef.current;
      if (listEl) {
        const options = listEl.querySelectorAll<HTMLElement>('[role="option"]');
        options[nextIndex]?.focus();
      }
    },
    [disabled, items, selectedIndex, onSelect],
  );

  if (loading) {
    return (
      <div className="space-y-1">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-8 animate-pulse rounded-lg bg-slate-100"
          />
        ))}
      </div>
    );
  }

  return (
    <ul
      ref={listRef}
      role="listbox"
      aria-label="Categorías de productos"
      aria-orientation="vertical"
      onKeyDown={handleKeyDown}
      className="space-y-0.5"
    >
      {items.map((item, idx) => {
        const isSelected = item.id === selectedId;
        return (
          <li
            key={item.id ?? '__all__'}
            id={`cat-option-${item.id ?? 'all'}`}
            role="option"
            aria-selected={isSelected}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => !disabled && onSelect(item.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (!disabled) onSelect(item.id);
              }
            }}
            className={[
              'flex cursor-pointer select-none items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1',
              isSelected
                ? 'bg-indigo-600 font-semibold text-white'
                : 'text-slate-700 hover:bg-slate-100',
              disabled ? 'pointer-events-none opacity-60' : '',
            ].join(' ')}
          >
            <span className="truncate">{item.label}</span>
            {item.count !== undefined && (
              <span
                className={[
                  'ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium',
                  isSelected
                    ? 'bg-indigo-500 text-indigo-100'
                    : 'bg-slate-200 text-slate-500',
                ].join(' ')}
              >
                {item.count}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
