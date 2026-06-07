"use client";

import { useMemo, useState } from 'react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { ApiError } from '@/lib/api/client';
import { cn } from '@/lib/utils';

import {
  getEffectiveRestaurantOperationSettings,
  useRestaurantOperationSettings,
  useUpdateRestaurantOperationSettings,
} from '../hooks';
import type { RestaurantOperationSettings } from '../types';

function normalizeSettings(settings: RestaurantOperationSettings): RestaurantOperationSettings {
  const normalized: RestaurantOperationSettings = { ...settings };

  if (!normalized.kitchen_enabled) {
    normalized.counter_orders_enabled = false;
  }

  if (!normalized.tables_enabled) {
    normalized.allow_dine_in_orders = false;
  }

  if (
    normalized.default_pos_mode === 'kitchen_order' &&
    (!normalized.kitchen_enabled || !normalized.counter_orders_enabled)
  ) {
    normalized.default_pos_mode = 'quick_sale';
  }

  return normalized;
}

function hasAtLeastOneOperationMode(settings: RestaurantOperationSettings): boolean {
  return Boolean(settings.pos_quick_sale_enabled || settings.counter_orders_enabled);
}

function statusLabel(checked: boolean): 'Activado' | 'Desactivado' {
  return checked ? 'Activado' : 'Desactivado';
}

function ToggleStatusPill({ checked }: { checked: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none',
        checked ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600',
      )}
    >
      {statusLabel(checked)}
    </span>
  );
}

function OperationToggleRow({
  title,
  description,
  checked,
  disabled,
  onCheckedChange,
  ariaLabel,
  note,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
  ariaLabel: string;
  note?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-4 rounded-xl border p-4 transition-colors',
        checked ? 'border-emerald-200 bg-emerald-50/60' : 'border-slate-200 bg-slate-50/60',
        disabled && 'opacity-60',
      )}
    >
      <div className="min-w-0 space-y-1">
        <p className="text-sm font-medium text-slate-900">{title}</p>
        <p className="text-xs text-slate-500">{description}</p>
        {note ? <p className="text-[11px] font-medium text-amber-700">{note}</p> : null}
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <ToggleStatusPill checked={checked} />
        <Switch
          checked={checked}
          disabled={disabled}
          onCheckedChange={onCheckedChange}
          aria-label={ariaLabel}
          className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-slate-300 focus-visible:ring-emerald-500"
        />
      </div>
    </div>
  );
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const payload = error.payload as { detail?: string; message?: string } | undefined;
    return payload?.detail ?? payload?.message ?? error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'No se pudo guardar la configuracion operativa.';
}

export function RestaurantOperationSettingsForm() {
  const settingsQuery = useRestaurantOperationSettings();
  const updateMutation = useUpdateRestaurantOperationSettings();

  const [draftOverride, setDraftOverride] = useState<RestaurantOperationSettings | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const baseSettings = useMemo(() => {
    if (!settingsQuery.data) return null;
    return normalizeSettings(getEffectiveRestaurantOperationSettings(settingsQuery.data));
  }, [settingsQuery.data]);

  const draft = draftOverride ?? baseSettings;

  const normalizedDraft = useMemo(() => {
    if (!draft) return null;
    return normalizeSettings(draft);
  }, [draft]);

  const canUseKitchenDefault = Boolean(
    normalizedDraft?.kitchen_enabled && normalizedDraft?.counter_orders_enabled,
  );

  const isDirty = useMemo(() => {
    if (!baseSettings || !normalizedDraft) return false;
    return JSON.stringify(baseSettings) !== JSON.stringify(normalizedDraft);
  }, [baseSettings, normalizedDraft]);

  function updateField<K extends keyof RestaurantOperationSettings>(
    key: K,
    value: RestaurantOperationSettings[K],
  ) {
    setSuccessMessage(null);
    setFormError(null);
    setDraftOverride((current) => {
      const source = current ?? baseSettings;
      if (!source) return source;
      return normalizeSettings({ ...source, [key]: value });
    });
  }

  async function handleSave() {
    if (!normalizedDraft) return;

    if (!hasAtLeastOneOperationMode(normalizedDraft)) {
      setFormError('El negocio necesita al menos un modo de operacion activo.');
      return;
    }

    setFormError(null);
    setSuccessMessage(null);

    try {
      const saved = await updateMutation.mutateAsync(normalizedDraft);
      const normalizedSaved = normalizeSettings(saved);
      setDraftOverride(normalizedSaved);
      setSuccessMessage('Configuracion operativa guardada correctamente.');
    } catch (error) {
      setFormError(toErrorMessage(error));
    }
  }

  if (settingsQuery.isLoading && !draft) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Cargando configuracion operativa...
      </div>
    );
  }

  if (settingsQuery.isError && !draft) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        No pudimos cargar la configuracion operativa.
        <button
          type="button"
          onClick={() => settingsQuery.refetch()}
          className="ml-3 rounded-full border border-rose-500 px-3 py-1 text-xs font-semibold text-rose-600"
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (!normalizedDraft) {
    return null;
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-slate-400">Restaurante inteligente</p>
        <h1 className="text-3xl font-semibold text-slate-900">Configuracion operativa</h1>
        <p className="text-sm text-slate-500">
          Defini como trabaja este local: con o sin mesas, con o sin cocina, venta rapida, retiro, salon y delivery.
        </p>
      </header>

      {successMessage ? (
        <Alert>
          <AlertTitle>Guardado</AlertTitle>
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      ) : null}

      {formError ? (
        <Alert variant="destructive">
          <AlertTitle>No se pudo guardar</AlertTitle>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Operacion principal</CardTitle>
          <CardDescription>
            Configura los modos principales del POS para este negocio.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <OperationToggleRow
            title="Usar venta rapida POS"
            description="Permite registrar ventas directas desde el POS sin enviarlas a cocina."
            checked={normalizedDraft.pos_quick_sale_enabled}
            onCheckedChange={(checked) => updateField('pos_quick_sale_enabled', checked)}
            ariaLabel="Usar venta rapida POS"
          />

          <div className="rounded-xl border border-slate-200 p-4">
            <label htmlFor="default-pos-mode" className="text-sm font-medium text-slate-900">
              Modo POS por defecto
            </label>
            <p className="mt-1 text-xs text-slate-500">
              Define el modo inicial para nuevas operaciones en el POS.
            </p>
            <select
              id="default-pos-mode"
              className="mt-3 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              value={normalizedDraft.default_pos_mode}
              onChange={(event) =>
                updateField('default_pos_mode', event.target.value as RestaurantOperationSettings['default_pos_mode'])
              }
            >
              <option value="quick_sale">Venta rapida</option>
              <option value="kitchen_order" disabled={!canUseKitchenDefault}>
                Pedido con cocina
              </option>
            </select>
            {!canUseKitchenDefault ? (
              <p className="mt-2 text-xs text-amber-700">
                Para usar Pedido con cocina como predeterminado, activa cocina y pedidos de mostrador con cocina.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cocina</CardTitle>
          <CardDescription>Define si el negocio opera con tablero KDS y pedidos a cocina.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <OperationToggleRow
            title="Usar Cocina / KDS"
            description="Activa el tablero de cocina para preparar pedidos."
            checked={normalizedDraft.kitchen_enabled}
            onCheckedChange={(checked) => updateField('kitchen_enabled', checked)}
            ariaLabel="Usar Cocina KDS"
          />

          <OperationToggleRow
            title="Permitir pedidos de mostrador con cocina"
            description="Permite enviar pedidos desde el POS a cocina."
            checked={normalizedDraft.counter_orders_enabled}
            disabled={!normalizedDraft.kitchen_enabled}
            onCheckedChange={(checked) => updateField('counter_orders_enabled', checked)}
            ariaLabel="Permitir pedidos de mostrador con cocina"
            note={!normalizedDraft.kitchen_enabled ? 'Deshabilitado porque Cocina / KDS está apagado.' : undefined}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mesas y salon</CardTitle>
          <CardDescription>Controla si el negocio opera con mapa de mesas y pedidos de salon.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <OperationToggleRow
            title="Usar mesas / salon"
            description="Activa mapa de mesas, pedidos de salon y configuracion de mesas."
            checked={normalizedDraft.tables_enabled}
            onCheckedChange={(checked) => updateField('tables_enabled', checked)}
            ariaLabel="Usar mesas salon"
          />

          <OperationToggleRow
            title="Permitir pedidos en salon"
            description="Permite crear pedidos asociados a mesas/salon."
            checked={normalizedDraft.allow_dine_in_orders}
            disabled={!normalizedDraft.tables_enabled}
            onCheckedChange={(checked) => updateField('allow_dine_in_orders', checked)}
            ariaLabel="Permitir pedidos en salon"
            note={!normalizedDraft.tables_enabled ? 'Deshabilitado porque Mesas / salón está apagado.' : undefined}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Canales</CardTitle>
          <CardDescription>Selecciona los canales operativos habilitados para recepcion de pedidos.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <OperationToggleRow
            title="Permitir retiro / pickup"
            description="Habilita pedidos para retirar en el local."
            checked={normalizedDraft.allow_pickup_orders}
            onCheckedChange={(checked) => updateField('allow_pickup_orders', checked)}
            ariaLabel="Permitir retiro pickup"
          />

          <OperationToggleRow
            title="Permitir delivery"
            description="Habilita pedidos de entrega a domicilio."
            checked={normalizedDraft.allow_delivery_orders}
            onCheckedChange={(checked) => updateField('allow_delivery_orders', checked)}
            ariaLabel="Permitir delivery"
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            if (!settingsQuery.data) return;
            setDraftOverride(baseSettings);
            setFormError(null);
            setSuccessMessage(null);
          }}
          disabled={!isDirty || updateMutation.isPending}
        >
          Descartar
        </Button>
        <Button
          type="button"
          onClick={() => void handleSave()}
          disabled={!isDirty || updateMutation.isPending}
        >
          {updateMutation.isPending ? 'Guardando...' : 'Guardar configuracion'}
        </Button>
      </div>
    </section>
  );
}

export { hasAtLeastOneOperationMode, normalizeSettings };
