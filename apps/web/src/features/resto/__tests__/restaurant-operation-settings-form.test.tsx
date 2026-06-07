import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RestaurantOperationSettings } from '@/features/resto/types';
import { RestaurantOperationSettingsForm } from '@/features/resto/components/restaurant-operation-settings-form';

const mocks = vi.hoisted(() => ({
  settings: {
    tables_enabled: true,
    kitchen_enabled: true,
    counter_orders_enabled: true,
    pos_quick_sale_enabled: true,
    allow_pickup_orders: true,
    allow_dine_in_orders: true,
    allow_delivery_orders: false,
    default_pos_mode: 'kitchen_order' as const,
  } satisfies RestaurantOperationSettings,
  mutateAsync: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => ({
    data: mocks.settings,
    isLoading: false,
    isError: false,
    refetch: mocks.refetch,
  }),
  useUpdateRestaurantOperationSettings: () => ({
    mutateAsync: mocks.mutateAsync,
    isPending: false,
  }),
  getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

describe('RestaurantOperationSettingsForm', () => {
  beforeEach(() => {
    mocks.mutateAsync.mockReset();
    mocks.refetch.mockReset();
    mocks.settings = {
      tables_enabled: true,
      kitchen_enabled: true,
      counter_orders_enabled: true,
      pos_quick_sale_enabled: true,
      allow_pickup_orders: true,
      allow_dine_in_orders: true,
      allow_delivery_orders: false,
      default_pos_mode: 'kitchen_order',
    };
  });

  it('renders loaded settings', () => {
    render(<RestaurantOperationSettingsForm />);

    expect(screen.getByRole('heading', { name: 'Configuracion operativa' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Usar Cocina KDS' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: 'Usar venta rapida POS' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Modo POS por defecto')).toHaveValue('kitchen_order');
    expect(screen.getAllByText('Activado').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText('Desactivado')).toBeInTheDocument();
  });

  it('normalizes kitchen off and sends corrected payload', async () => {
    mocks.mutateAsync.mockImplementation(async (payload: RestaurantOperationSettings) => payload);

    render(<RestaurantOperationSettingsForm />);

    fireEvent.click(screen.getByRole('switch', { name: 'Usar Cocina KDS' }));

    expect(screen.getByRole('switch', { name: 'Permitir pedidos de mostrador con cocina' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: 'Permitir pedidos de mostrador con cocina' })).toBeDisabled();
    expect(screen.getByLabelText('Modo POS por defecto')).toHaveValue('quick_sale');
    expect(screen.getByText('Deshabilitado porque Cocina / KDS está apagado.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuracion' }));

    await waitFor(() => {
      expect(mocks.mutateAsync).toHaveBeenCalledTimes(1);
    });

    expect(mocks.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        kitchen_enabled: false,
        counter_orders_enabled: false,
        default_pos_mode: 'quick_sale',
      }),
    );
  });

  it('normalizes tables off and disables dine-in', async () => {
    mocks.mutateAsync.mockImplementation(async (payload: RestaurantOperationSettings) => payload);

    render(<RestaurantOperationSettingsForm />);

    fireEvent.click(screen.getByRole('switch', { name: 'Usar mesas salon' }));

    expect(screen.getByRole('switch', { name: 'Permitir pedidos en salon' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: 'Permitir pedidos en salon' })).toBeDisabled();
    expect(screen.getByText('Deshabilitado porque Mesas / salón está apagado.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuracion' }));

    await waitFor(() => {
      expect(mocks.mutateAsync).toHaveBeenCalledTimes(1);
    });

    expect(mocks.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        tables_enabled: false,
        allow_dine_in_orders: false,
      }),
    );
  });

  it('blocks save when all operation modes are disabled', async () => {
    render(<RestaurantOperationSettingsForm />);

    fireEvent.click(screen.getByRole('switch', { name: 'Usar Cocina KDS' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Usar venta rapida POS' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuracion' }));

    expect(mocks.mutateAsync).not.toHaveBeenCalled();
    expect(await screen.findByText('El negocio necesita al menos un modo de operacion activo.')).toBeInTheDocument();
  });

  it('shows success and backend error feedback', async () => {
    mocks.mutateAsync.mockResolvedValueOnce({
      ...mocks.settings,
      default_pos_mode: 'quick_sale',
    });

    render(<RestaurantOperationSettingsForm />);

    fireEvent.click(screen.getByRole('switch', { name: 'Usar Cocina KDS' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuracion' }));

    expect(await screen.findByText('Configuracion operativa guardada correctamente.')).toBeInTheDocument();

    mocks.mutateAsync.mockRejectedValueOnce(new Error('Error al guardar'));

    fireEvent.click(screen.getByRole('switch', { name: 'Usar Cocina KDS' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuracion' }));

    expect(await screen.findByText('Error al guardar')).toBeInTheDocument();
  });
});
