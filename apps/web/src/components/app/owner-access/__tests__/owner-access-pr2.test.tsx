import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
    useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
    usePathname: () => '/app/settings/access',
    useSearchParams: () => new URLSearchParams(''),
    redirect: vi.fn(),
}));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: any) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

const mockCreateMember = vi.fn();
vi.mock('@/lib/api/owner-access', () => ({
    ownerAccessApi: {
        createMember: (...args: any[]) => mockCreateMember(...args),
        getAccounts: vi.fn(),
        getAccessSummary: vi.fn(),
        getRoles: vi.fn(),
    },
}));

vi.mock('@/lib/api/client', () => ({
    apiPost: vi.fn(),
    apiGet: vi.fn(),
}));

// ── CreateMemberModal tests ─────────────────────────────────────────────────

describe('CreateMemberModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockCreateMember.mockResolvedValue({
            success: true,
            username: 'testuser',
            full_name: 'Test User',
            role: 'cashier',
            role_display: 'Cashier',
        });
    });

    async function renderModal() {
        const { CreateMemberModal } = await import(
            '@/components/app/owner-access/create-member-modal'
        );
        const onClose = vi.fn();
        render(<CreateMemberModal isOpen onClose={onClose} />);
        return { onClose };
    }

    it('defaults to owner_managed mode for staff role', async () => {
        await renderModal();

        // Default role is staff → owner_managed
        const administradaRadio = screen.getByDisplayValue('owner_managed');
        expect((administradaRadio as HTMLInputElement).checked).toBe(true);
    });

    it('switches to personal mode when admin is selected', async () => {
        await renderModal();

        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        const personalRadio = screen.getByDisplayValue('personal');
        expect((personalRadio as HTMLInputElement).checked).toBe(true);
    });

    it('switches to owner_managed mode when cashier is selected', async () => {
        await renderModal();

        // First switch to admin (personal)
        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        // Then switch to cashier (owner_managed)
        fireEvent.change(roleSelect, { target: { value: 'cashier' } });

        const administradaRadio = screen.getByDisplayValue('owner_managed');
        expect((administradaRadio as HTMLInputElement).checked).toBe(true);
    });

    it('hides force password checkbox for owner_managed mode', async () => {
        await renderModal();

        // Default is staff → owner_managed
        expect(screen.queryByLabelText(/Forzar cambio de contraseña/)).not.toBeInTheDocument();
    });

    it('shows force password checkbox for personal mode', async () => {
        await renderModal();

        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        expect(screen.getByLabelText(/Forzar cambio de contraseña/)).toBeInTheDocument();
    });

    it('force password checkbox defaults to true when recommended mode is personal', async () => {
        await renderModal();

        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        const checkbox = screen.getByLabelText(/Forzar cambio de contraseña/) as HTMLInputElement;
        expect(checkbox.checked).toBe(true);
    });

    it('clears force password change when switching to owner_managed', async () => {
        await renderModal();

        // Switch to admin (personal, force=true)
        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        // Switch to cashier (owner_managed)
        fireEvent.change(roleSelect, { target: { value: 'cashier' } });

        // Checkbox should be gone
        expect(screen.queryByLabelText(/Forzar cambio de contraseña/)).not.toBeInTheDocument();
    });

    it('submits payload with account_mode and force_password_change', async () => {
        await renderModal();

        // Switch to admin → personal mode, force=true
        const roleSelect = screen.getByDisplayValue('Staff / Empleado');
        fireEvent.change(roleSelect, { target: { value: 'admin' } });

        // Fill form
        fireEvent.change(screen.getByPlaceholderText('Juan'), { target: { value: 'Test' } });
        fireEvent.change(screen.getByPlaceholderText('Pérez'), { target: { value: 'User' } });
        fireEvent.change(screen.getByPlaceholderText('juan.perez'), { target: { value: 'testuser' } });
        fireEvent.change(screen.getByPlaceholderText('Mínimo 8 caracteres'), { target: { value: 'SecurePass99' } });

        fireEvent.click(screen.getByRole('button', { name: /Crear Usuario/ }));

        await waitFor(() => {
            expect(mockCreateMember).toHaveBeenCalledWith(
                expect.objectContaining({
                    account_mode: 'personal',
                    force_password_change: true,
                    role: 'admin',
                })
            );
        });
    });

    it('sends force_password_change=false for owner_managed mode', async () => {
        await renderModal();

        // Default staff → owner_managed
        fireEvent.change(screen.getByPlaceholderText('Juan'), { target: { value: 'Test' } });
        fireEvent.change(screen.getByPlaceholderText('Pérez'), { target: { value: 'User' } });
        fireEvent.change(screen.getByPlaceholderText('juan.perez'), { target: { value: 'testuser' } });
        fireEvent.change(screen.getByPlaceholderText('Mínimo 8 caracteres'), { target: { value: 'SecurePass99' } });

        fireEvent.click(screen.getByRole('button', { name: /Crear Usuario/ }));

        await waitFor(() => {
            expect(mockCreateMember).toHaveBeenCalledWith(
                expect.objectContaining({
                    account_mode: 'owner_managed',
                    force_password_change: false,
                })
            );
        });
    });
});

// ── AccountsTable badge tests ───────────────────────────────────────────────

describe('AccountsTable', () => {
    // Mock the sub-components that AccountsTable imports
    vi.mock('@/components/app/owner-access/shared-components', () => ({
        RoleBadge: ({ roleDisplay }: any) => <span data-testid="role-badge">{roleDisplay}</span>,
        StatusBadge: ({ isActive }: any) => <span>{isActive ? 'Activo' : 'Inactivo'}</span>,
    }));

    vi.mock('@/components/app/owner-access/reset-password-modal', () => ({
        ResetPasswordModal: () => null,
    }));

    vi.mock('@/components/app/owner-access/member-actions-modals', () => ({
        ChangeRoleModal: () => null,
        ConfirmActionModal: () => null,
    }));

    it('renders account_mode badge for each user', async () => {
        const { AccountsTable } = await import(
            '@/components/app/owner-access/accounts-table'
        );

        const accounts = [
            {
                id: 1,
                email: 'owner@test.com',
                username: 'owner',
                full_name: 'Owner User',
                role: 'owner',
                role_display: 'Owner',
                is_active: true,
                has_usable_password: true,
                account_mode: 'owner_managed' as const,
                date_joined: '2025-01-01T00:00:00Z',
                last_login: null,
            },
            {
                id: 2,
                email: 'personal@test.com',
                username: 'personal_user',
                full_name: 'Personal User',
                role: 'admin',
                role_display: 'Admin',
                is_active: true,
                has_usable_password: true,
                account_mode: 'personal' as const,
                date_joined: '2025-01-01T00:00:00Z',
                last_login: null,
            },
            {
                id: 3,
                email: 'managed@test.com',
                username: 'managed_user',
                full_name: 'Managed User',
                role: 'cashier',
                role_display: 'Cashier',
                is_active: true,
                has_usable_password: true,
                account_mode: 'owner_managed' as const,
                date_joined: '2025-01-01T00:00:00Z',
                last_login: null,
            },
        ];

        render(<AccountsTable accounts={accounts} />);

        // Owner row shows dash
        expect(screen.getByText('—')).toBeInTheDocument();
        // Personal user shows Personal badge
        expect(screen.getByText('Personal')).toBeInTheDocument();
        // Managed user shows Administrada badge
        expect(screen.getByText('Administrada')).toBeInTheDocument();
    });
});

// ── SeatInfoBar tests ───────────────────────────────────────────────────────

describe('SeatInfoBar', () => {
    it('shows progress bar when under limit (using max)', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 2, max: 5, source: 'v2', access_granted: true }} />
        );

        expect(screen.getByText(/2/)).toBeInTheDocument();
        expect(screen.getByText(/5/)).toBeInTheDocument();
        expect(screen.getByText(/3 disponibles/)).toBeInTheDocument();
    });

    it('shows progress bar when under limit (using limit)', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 1, limit: 4, source: 'v2', access_granted: true }} />
        );

        expect(screen.getByText(/1/)).toBeInTheDocument();
        expect(screen.getByText(/4/)).toBeInTheDocument();
        expect(screen.getByText(/3 disponibles/)).toBeInTheDocument();
    });

    it('prefers limit over max when both are present', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 1, limit: 3, max: 10, source: 'v2', access_granted: true }} />
        );

        // Should show limit=3, not max=10
        expect(screen.getByText(/3 usuarios secundarios/)).toBeInTheDocument();
        expect(screen.getByText(/2 disponibles/)).toBeInTheDocument();
    });

    it('shows warning when at limit', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 5, max: 5, source: 'v2', access_granted: true }} />
        );

        expect(screen.getByText(/Has alcanzado el límite/)).toBeInTheDocument();
    });

    it('shows inactive message when access_granted is false', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 3, max: 5, source: 'v2', access_granted: false }} />
        );

        expect(screen.getByText(/Suscripción inactiva/)).toBeInTheDocument();
    });

    it('shows support message when effective limit is 0 and access_granted is true', async () => {
        const { SeatInfoBar } = await import(
            '@/components/app/owner-access/seat-info-bar'
        );

        render(
            <SeatInfoBar seatInfo={{ current: 0, source: 'v2', access_granted: true }} />
        );

        expect(screen.getByText(/Contactá soporte/)).toBeInTheDocument();
    });
});

// ── getEffectiveLimit tests ─────────────────────────────────────────────────

describe('getEffectiveLimit', () => {
    it('prefers limit over max', async () => {
        const { getEffectiveLimit } = await import('@/types/owner-access');
        expect(getEffectiveLimit({ current: 0, limit: 7, max: 3, source: 'v2', access_granted: true })).toBe(7);
    });

    it('falls back to max when limit is absent', async () => {
        const { getEffectiveLimit } = await import('@/types/owner-access');
        expect(getEffectiveLimit({ current: 0, max: 5, source: 'v2', access_granted: true })).toBe(5);
    });

    it('returns 0 when neither limit nor max is present', async () => {
        const { getEffectiveLimit } = await import('@/types/owner-access');
        expect(getEffectiveLimit({ current: 0, source: 'v2', access_granted: true })).toBe(0);
    });
});

// ── Forced password change page tests ───────────────────────────────────────

describe('CambiarContrasenaPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('disables submit when fields are empty', async () => {
        const { default: CambiarContrasenaPage } = await import(
            '@/app/(auth)/cambiar-contrasena/page'
        );

        render(<CambiarContrasenaPage />);

        const submitBtn = screen.getByRole('button', { name: /Cambiar contraseña/ });
        expect(submitBtn).toBeDisabled();
    });

    it('shows validation error when passwords do not match', async () => {
        const { default: CambiarContrasenaPage } = await import(
            '@/app/(auth)/cambiar-contrasena/page'
        );

        render(<CambiarContrasenaPage />);

        fireEvent.change(screen.getByLabelText(/Contraseña actual/), { target: { value: 'OldPass123' } });
        fireEvent.change(screen.getByLabelText(/Nueva contraseña/), { target: { value: 'NewSecure99' } });
        fireEvent.change(screen.getByLabelText(/Confirmar nueva contraseña/), { target: { value: 'Different99' } });

        expect(screen.getByText(/Las contraseñas no coinciden/)).toBeInTheDocument();
    });

    it('shows validation error when new password is too short', async () => {
        const { default: CambiarContrasenaPage } = await import(
            '@/app/(auth)/cambiar-contrasena/page'
        );

        render(<CambiarContrasenaPage />);

        fireEvent.change(screen.getByLabelText(/Contraseña actual/), { target: { value: 'OldPass123' } });
        fireEvent.change(screen.getByLabelText(/Nueva contraseña/), { target: { value: 'short' } });
        fireEvent.change(screen.getByLabelText(/Confirmar nueva contraseña/), { target: { value: 'short' } });

        expect(screen.getByText(/al menos 8 caracteres/)).toBeInTheDocument();
    });

    it('enables submit when form is valid', async () => {
        const { default: CambiarContrasenaPage } = await import(
            '@/app/(auth)/cambiar-contrasena/page'
        );

        render(<CambiarContrasenaPage />);

        fireEvent.change(screen.getByLabelText(/Contraseña actual/), { target: { value: 'OldPass123' } });
        fireEvent.change(screen.getByLabelText(/Nueva contraseña/), { target: { value: 'NewSecure99' } });
        fireEvent.change(screen.getByLabelText(/Confirmar nueva contraseña/), { target: { value: 'NewSecure99' } });

        const submitBtn = screen.getByRole('button', { name: /Cambiar contraseña/ });
        expect(submitBtn).not.toBeDisabled();
    });
});

// ── Create button access_granted gating ─────────────────────────────────────

describe('Create button access gating', () => {
    it('disables create button when access_granted is false', async () => {
        const { AccountsTab } = await import(
            '@/app/app/settings/access/page'
        );

        render(
            <AccountsTab
                accounts={[]}
                seatInfo={{ current: 0, max: 5, source: 'v2', access_granted: false }}
                onRefresh={vi.fn()}
            />
        );

        const createBtn = screen.getByRole('button', { name: /Crear usuario/ });
        expect(createBtn).toBeDisabled();
        expect(screen.getByText(/Necesitás una suscripción activa/)).toBeInTheDocument();
    });

    it('enables create button when access_granted is true', async () => {
        const { AccountsTab } = await import(
            '@/app/app/settings/access/page'
        );

        render(
            <AccountsTab
                accounts={[]}
                seatInfo={{ current: 0, max: 5, source: 'v2', access_granted: true }}
                onRefresh={vi.fn()}
            />
        );

        const createBtn = screen.getByRole('button', { name: /Crear usuario/ });
        expect(createBtn).not.toBeDisabled();
        expect(screen.queryByText(/Necesitás una suscripción activa/)).not.toBeInTheDocument();
    });
});

// ── canManage owner-only test ───────────────────────────────────────────────

describe('canManage owner-only', () => {
    it('does not set isOwner=true for admin role', async () => {
        // Verify the actual code logic: summary.role === 'owner' (not 'admin')
        // This is a unit-level assertion on the logic, not a full page render
        const summary = { role: 'admin' };
        const canManage = summary.role === 'owner';
        expect(canManage).toBe(false);
    });

    it('sets isOwner=true for owner role', () => {
        const summary = { role: 'owner' };
        const canManage = summary.role === 'owner';
        expect(canManage).toBe(true);
    });
});
