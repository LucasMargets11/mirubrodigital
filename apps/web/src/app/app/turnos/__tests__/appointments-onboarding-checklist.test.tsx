import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppointmentsOnboardingChecklist } from '../appointments-onboarding-checklist';

const mocks = vi.hoisted(() => ({
  useStatus: vi.fn(),
}));

vi.mock('@/features/appointments/hooks', () => ({
  useAppointmentOnboardingStatus: mocks.useStatus,
}));

const readyStatus = {
  active_services_count: 1,
  has_active_services: true,
  has_reservable_service: true,
  has_valid_availability: true,
  active_professionals_count: 0,
  public_booking_available: true,
  ready_to_receive_bookings: true,
};

describe('AppointmentsOnboardingChecklist', () => {
  beforeEach(() => {
    mocks.useStatus.mockReset();
  });

  it('shows incomplete essentials and explains that professionals are optional', () => {
    mocks.useStatus.mockReturnValue({
      data: {
        ...readyStatus,
        has_active_services: false,
        has_reservable_service: false,
        public_booking_available: false,
        ready_to_receive_bookings: false,
      },
      isPending: false,
      isError: false,
    });

    render(<AppointmentsOnboardingChecklist />);

    expect(screen.getByText('1 de 3 pasos esenciales completados')).toBeInTheDocument();
    expect(
      screen.getByText('Podés agregar profesionales si necesitás agendas separadas.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configurar servicios' })).toHaveAttribute(
      'href',
      '/app/turnos/servicios',
    );
    expect(screen.getByRole('link', { name: 'Configurar horarios' })).toHaveAttribute(
      'href',
      '/app/turnos/horarios',
    );
    expect(screen.getByRole('link', { name: 'Ver link de reservas' })).toHaveAttribute(
      'href',
      '#public-booking-link',
    );
    expect(
      screen.queryByText('Tu agenda está lista para recibir reservas.'),
    ).not.toBeInTheDocument();
  });

  it('marks an agenda ready without requiring professionals', () => {
    mocks.useStatus.mockReturnValue({
      data: readyStatus,
      isPending: false,
      isError: false,
    });

    render(<AppointmentsOnboardingChecklist />);

    expect(screen.getByText('Tu agenda está lista para recibir reservas.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver agenda' })).toHaveAttribute(
      'href',
      '/app/turnos/turnos',
    );
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
  });

  it('can be dismissed without navigating away', () => {
    mocks.useStatus.mockReturnValue({ data: readyStatus, isPending: false, isError: false });

    render(<AppointmentsOnboardingChecklist />);
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar guía de primeros pasos' }));

    expect(screen.queryByTestId('turnos-onboarding-checklist')).not.toBeInTheDocument();
  });

  it('surfaces status errors and allows a retry', () => {
    const refetch = vi.fn();
    mocks.useStatus.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      refetch,
    });

    render(<AppointmentsOnboardingChecklist />);
    fireEvent.click(screen.getByRole('button', { name: 'Volver a intentar' }));

    expect(refetch).toHaveBeenCalledOnce();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No pudimos comprobar el estado de configuración.',
    );
  });
});
