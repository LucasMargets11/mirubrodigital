import { render, screen, fireEvent } from '@testing-library/react';
import { beforeAll, beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
    useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/lib/auth/client', () => ({
    login: vi.fn(),
    register: vi.fn(),
    googleAuth: vi.fn(),
}));

beforeAll(() => {
    class ResizeObserverMock {
        observe() {}
        disconnect() {}
        unobserve() {}
    }

    // jsdom doesn't provide ResizeObserver by default.
    // @ts-expect-error test runtime shim
    global.ResizeObserver = ResizeObserverMock;
});

describe('AuthForm beta Google-only flag', () => {
    const originalFlag = process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY;

    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        if (originalFlag === undefined) {
            delete process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY;
        } else {
            process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY = originalFlag;
        }
    });

    it('shows only Google + secondary internal entry when flag is true', async () => {
        process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY = 'true';
        const { AuthForm } = await import('@/components/auth/auth-form');

        render(<AuthForm />);

        expect(screen.getByText('Continuar con Google')).toBeInTheDocument();
        expect(screen.getByText('Ingreso interno/demo')).toBeInTheDocument();

        expect(screen.queryByText('Crear cuenta')).not.toBeInTheDocument();
        expect(screen.queryByText('¿Olvidaste tu contraseña?')).not.toBeInTheDocument();

        fireEvent.click(screen.getByText('Ingreso interno/demo'));

        expect(screen.getByText('Ingreso interno/demo')).toBeInTheDocument();
        expect(screen.getByLabelText('Email o usuario')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Ingresar con contraseña' })).toBeInTheDocument();
    });

    it('keeps legacy login/signup UI when flag is false', async () => {
        process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY = 'false';
        const { AuthForm } = await import('@/components/auth/auth-form');

        render(<AuthForm />);

        expect(screen.getByLabelText('Email o usuario')).toBeInTheDocument();
        expect(screen.getByText('Crear cuenta')).toBeInTheDocument();
        expect(screen.getByText('¿Olvidaste tu contraseña?')).toBeInTheDocument();
        expect(screen.getByText('Continuar con Google')).toBeInTheDocument();

        expect(screen.queryByText('Ingreso interno/demo')).not.toBeInTheDocument();
    });
});
