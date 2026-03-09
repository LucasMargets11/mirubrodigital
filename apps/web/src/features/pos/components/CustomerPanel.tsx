'use client';

/**
 * CustomerPanel
 *
 * Customer type selector (consumer / registered) + customer search combobox
 * for the POS New Sale screen.
 *
 * Accessibility:
 * - Radio group uses <fieldset>/<legend>.
 * - Customer combobox has a real <label>.
 * - Dropdown uses role="listbox"/role="option".
 * - "Crear cliente" button returns focus correctly via CreateCustomerDialog.
 */

import { useEffect, useRef, useState } from 'react';
import { usePosCustomers } from '@/features/pos/cash-hooks';
import type { PosCustomerSummary } from '@/types/pos-cash';
import { CreateCustomerDialog } from './CreateCustomerDialog';

export type CustomerType = 'consumer' | 'registered';

interface CustomerPanelProps {
  customerType: CustomerType;
  onCustomerTypeChange: (type: CustomerType) => void;
  customer: PosCustomerSummary | null;
  onCustomerChange: (customer: PosCustomerSummary | null) => void;
  disabled?: boolean;
}

export function CustomerPanel({
  customerType,
  onCustomerTypeChange,
  customer,
  onCustomerChange,
  disabled,
}: CustomerPanelProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [focusedIdx, setFocusedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const createBtnRef = useRef<HTMLButtonElement>(null);

  const customersQuery = usePosCustomers(searchQuery);
  const results = customersQuery.data?.results ?? [];

  // Reset search when customer type changes back to consumer
  useEffect(() => {
    if (customerType === 'consumer') {
      setSearchQuery('');
      setDropdownOpen(false);
      onCustomerChange(null);
    }
  }, [customerType, onCustomerChange]);

  // Open dropdown when we have results
  useEffect(() => {
    if (searchQuery.length >= 2) {
      setDropdownOpen(true);
      setFocusedIdx(-1);
    } else {
      setDropdownOpen(false);
    }
  }, [searchQuery]);

  function selectCustomer(c: PosCustomerSummary) {
    onCustomerChange(c);
    setSearchQuery('');
    setDropdownOpen(false);
  }

  function clearCustomer() {
    onCustomerChange(null);
    setSearchQuery('');
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!dropdownOpen || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && focusedIdx >= 0) {
      e.preventDefault();
      selectCustomer(results[focusedIdx]);
    } else if (e.key === 'Escape') {
      setDropdownOpen(false);
      setFocusedIdx(-1);
    }
  }

  const listId = 'customer-search-results';

  return (
    <fieldset>
      <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Tipo de cliente
      </legend>

      {/* Radio group */}
      <div className="flex gap-3" role="radiogroup">
        {[
          { value: 'consumer' as CustomerType, label: 'Consumidor final' },
          { value: 'registered' as CustomerType, label: 'Cliente registrado' },
        ].map(({ value, label }) => (
          <label
            key={value}
            className={`flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-sm font-medium transition-colors ${
              customerType === value
                ? 'border-slate-800 bg-slate-900 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
          >
            <input
              type="radio"
              name="pos-customer-type"
              value={value}
              checked={customerType === value}
              onChange={() => onCustomerTypeChange(value)}
              disabled={disabled}
              className="sr-only"
            />
            {label}
          </label>
        ))}
      </div>

      {/* Customer search (only when registered) */}
      {customerType === 'registered' && (
        <div className="mt-3 space-y-2">
          {/* Selected customer chip */}
          {customer ? (
            <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2.5">
              <div>
                <p className="text-sm font-semibold text-emerald-900">{customer.name}</p>
                {(customer.phone || customer.email) && (
                  <p className="text-xs text-emerald-600">
                    {customer.phone || customer.email}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={clearCustomer}
                disabled={disabled}
                aria-label="Cambiar cliente seleccionado"
                className="ml-2 rounded-full p-1 text-emerald-600 hover:bg-emerald-100 disabled:opacity-60"
              >
                <span aria-hidden>✕</span>
              </button>
            </div>
          ) : (
            <div className="relative">
              <label htmlFor="customer-combobox" className="sr-only">
                Buscar cliente registrado
              </label>
              <input
                id="customer-combobox"
                ref={inputRef}
                type="search"
                autoComplete="off"
                placeholder="Buscar cliente por nombre, email o teléfono…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                onFocus={() => searchQuery.length >= 2 && setDropdownOpen(true)}
                disabled={disabled}
                role="combobox"
                aria-expanded={dropdownOpen && results.length > 0}
                aria-controls={listId}
                aria-activedescendant={
                  focusedIdx >= 0 ? `customer-option-${results[focusedIdx]?.id}` : undefined
                }
                aria-autocomplete="list"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
              />

              {/* Loading */}
              {customersQuery.isLoading && (
                <p className="mt-1 text-xs text-slate-400 animate-pulse" aria-live="polite">
                  Buscando…
                </p>
              )}

              {/* Empty */}
              {searchQuery.length >= 2 && !customersQuery.isLoading && results.length === 0 && (
                <p className="mt-1 text-xs text-slate-400" aria-live="polite">
                  Sin resultados. Podés crear este cliente.
                </p>
              )}

              {/* Dropdown */}
              {dropdownOpen && results.length > 0 && (
                <ul
                  id={listId}
                  role="listbox"
                  aria-label="Clientes encontrados"
                  className="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg divide-y divide-slate-50"
                >
                  {results.map((c, idx) => (
                    <li
                      key={c.id}
                      id={`customer-option-${c.id}`}
                      role="option"
                      aria-selected={focusedIdx === idx}
                    >
                      <button
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => selectCustomer(c)}
                        disabled={disabled}
                        className={`flex w-full flex-col gap-0.5 px-3 py-2.5 text-left hover:bg-slate-50 ${
                          focusedIdx === idx ? 'bg-slate-50' : ''
                        }`}
                      >
                        <span className="text-sm font-medium text-slate-900">{c.name}</span>
                        {(c.phone || c.email) && (
                          <span className="text-xs text-slate-400">
                            {c.phone || c.email}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Create customer button */}
          {!customer && (
            <button
              ref={createBtnRef}
              type="button"
              onClick={() => setDialogOpen(true)}
              disabled={disabled}
              className="w-full rounded-xl border border-dashed border-slate-300 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-400 hover:bg-slate-50 disabled:opacity-60"
            >
              + Crear cliente nuevo
            </button>
          )}
        </div>
      )}

      {/* Create customer dialog */}
      <CreateCustomerDialog
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          // Return focus to the button that opened the dialog
          setTimeout(() => createBtnRef.current?.focus(), 50);
        }}
        onCreated={(newCustomer) => {
          setDialogOpen(false);
          selectCustomer(newCustomer);
        }}
      />
    </fieldset>
  );
}
