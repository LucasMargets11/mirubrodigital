'use client';

import { useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { KitchenBoard } from '@/app/app/kitchen/components/kitchen-board';
import { KitchenHero } from '@/app/app/kitchen/components/kitchen-hero';
import { Button } from '@/components/ui/button';
import {
  getEffectiveRestaurantOperationSettings,
  useRestaurantOperationSettings,
} from '@/features/resto/hooks';
import {
  posFetchKitchenBoard,
  posUpdateKitchenItemStatus,
  posUpdateKitchenOrderBulk,
} from '@/lib/api/pos';

import { useEmployeeSession } from '../context';

const KITCHEN_ALLOWED_ROLES = new Set(['kitchen', 'manager_op']);

export function KitchenTerminalPage() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const queryClient = useQueryClient();
  const { session, logout } = useEmployeeSession();

  const operationSettingsQuery = useRestaurantOperationSettings({
    enabled: session.status === 'authenticated',
  });
  const operationSettings = getEffectiveRestaurantOperationSettings(operationSettingsQuery.data);
  const kitchenEnabled = operationSettings.kitchen_enabled;

  const roleType = session.status === 'authenticated' ? session.employee.role_type : null;
  const canAccessKitchen = roleType ? KITCHEN_ALLOWED_ROLES.has(roleType) : false;

  const kitchenBoardQuery = useQuery({
    queryKey: ['pos', 'kitchen-board', session.status === 'authenticated' ? session.token : null],
    queryFn: () => {
      if (session.status !== 'authenticated') return Promise.resolve([]);
      return posFetchKitchenBoard(session.token);
    },
    enabled: session.status === 'authenticated' && canAccessKitchen && kitchenEnabled,
    refetchInterval: autoRefresh ? 3000 : false,
    refetchOnWindowFocus: true,
  });

  const updateItemMutation = useMutation({
    mutationFn: ({ itemId, status }: { itemId: string; status: 'pending' | 'in_progress' | 'ready' | 'done' | 'cancelled' }) => {
      if (session.status !== 'authenticated') {
        throw new Error('Sesión no autenticada');
      }
      return posUpdateKitchenItemStatus(session.token, itemId, status);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'kitchen-board'] });
    },
  });

  const updateOrderMutation = useMutation({
    mutationFn: ({ orderId, status }: { orderId: string; status: 'pending' | 'in_progress' | 'ready' | 'done' | 'cancelled' }) => {
      if (session.status !== 'authenticated') {
        throw new Error('Sesión no autenticada');
      }
      return posUpdateKitchenOrderBulk(session.token, orderId, status);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'kitchen-board'] });
    },
  });

  const metrics = useMemo(() => {
    const counts = {
      pending: 0,
      inProgress: 0,
      ready: 0,
    };

    (kitchenBoardQuery.data ?? []).forEach((order) => {
      order.items.forEach((item) => {
        if (item.kitchen_status === 'pending') counts.pending += 1;
        if (item.kitchen_status === 'in_progress') counts.inProgress += 1;
        if (item.kitchen_status === 'ready') counts.ready += 1;
      });
    });

    return counts;
  }, [kitchenBoardQuery.data]);

  if (session.status !== 'authenticated') {
    return null;
  }

  if (!canAccessKitchen) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-lg font-semibold">Acceso restringido</h1>
          <p className="mt-2 text-sm">
            Tu perfil operativo no tiene permisos de cocina para usar esta terminal.
          </p>
          <div className="mt-4">
            <Button type="button" variant="outline" onClick={logout}>
              Cerrar sesión
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 lg:p-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Empleado activo</p>
              <p className="text-sm font-semibold text-slate-900">
                {session.employee.display_name} · Cocina
              </p>
              <p className="text-xs text-slate-500">{session.employee.business_name}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={() => kitchenBoardQuery.refetch()}>
                Actualizar
              </Button>
              <Button type="button" variant="outline" onClick={logout}>
                Cerrar sesión
              </Button>
            </div>
          </div>
        </div>

        {!kitchenEnabled ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
            Cocina desactivada para este negocio.
          </div>
        ) : null}

        <KitchenHero
          metrics={metrics}
          isConnected={!kitchenBoardQuery.isError}
          isUpdating={kitchenBoardQuery.isRefetching || kitchenBoardQuery.isLoading}
          lastUpdated={kitchenBoardQuery.dataUpdatedAt ? new Date(kitchenBoardQuery.dataUpdatedAt) : undefined}
          onRefresh={kitchenBoardQuery.refetch}
          autoRefresh={autoRefresh}
          toggleAutoRefresh={() => setAutoRefresh((prev) => !prev)}
        />

        {!kitchenEnabled ? (
          <div className="flex h-[45vh] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white text-slate-500">
            El tablero de cocina está deshabilitado para esta operación.
          </div>
        ) : kitchenBoardQuery.isLoading && !kitchenBoardQuery.data ? (
          <div className="flex h-[45vh] items-center justify-center text-slate-400">
            Cargando tablero...
          </div>
        ) : (kitchenBoardQuery.data ?? []).length === 0 ? (
          <div className="flex h-[45vh] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white text-sm text-slate-500">
            No hay pedidos pendientes en cocina.
          </div>
        ) : (
          <div className="h-[calc(100vh-19rem)]">
            <KitchenBoard
              orders={kitchenBoardQuery.data ?? []}
              onUpdateItem={(id, status) => updateItemMutation.mutate({ itemId: id, status })}
              onUpdateOrder={(id, status) => updateOrderMutation.mutate({ orderId: id, status })}
            />
          </div>
        )}
      </div>
    </div>
  );
}
