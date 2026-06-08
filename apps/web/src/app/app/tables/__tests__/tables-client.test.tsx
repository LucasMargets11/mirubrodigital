import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mockUseRestaurantOperationSettings = vi.fn();
const mockUseRestaurantTablesMapState = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => mockUseRestaurantOperationSettings(),
  getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

vi.mock('@/features/tables/hooks', () => ({
  useRestaurantTablesMapState: () => mockUseRestaurantTablesMapState(),
}));

vi.mock('@/components/tables/tables-map', () => ({
  TablesMap: () => <div data-testid="tables-map" />,
}));

import { TablesClient } from '@/app/app/tables/tables-client';

describe('TablesClient', () => {
  it('shows operation settings copy and link when tables are disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: {
        tables_enabled: false,
        kitchen_enabled: true,
        counter_orders_enabled: true,
        pos_quick_sale_enabled: true,
        allow_pickup_orders: true,
        allow_dine_in_orders: false,
        allow_delivery_orders: false,
        default_pos_mode: 'quick_sale',
      },
    });

    mockUseRestaurantTablesMapState.mockReturnValue({
      data: { tables: [], layout: null },
      isLoading: false,
      isError: false,
    });

    render(<TablesClient />);

    expect(screen.getByText('El módulo de mesas está desactivado.')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Configuración operativa del restaurante' })
    ).toHaveAttribute('href', '/app/resto/settings/operation');
  });
});
