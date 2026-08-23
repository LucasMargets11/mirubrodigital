import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { googleAuthMock, googlePreauthorizedLoginMock } = vi.hoisted(() => ({
    googleAuthMock: vi.fn(),
    googlePreauthorizedLoginMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
    useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/lib/auth/client', () => ({
    login: vi.fn(),
    register: vi.fn(),
    googleAuth: googleAuthMock,
    googlePreauthorizedLogin: googlePreauthorizedLoginMock,
}));

type GoogleCallback = (response: { credential: string }) => Promise<void>;

describe('/entrar/cliente — ADMIN-CLIENTES 04D Google access', () => {
    const assignMock = vi.fn();
    const initializeMock = vi.fn();
    const renderButtonMock = vi.fn((parent: HTMLElement) => {
        parent.appendChild(document.createElement('div'));
    });
    const originalLocation = window.location;
    const originalClientId = process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID;
    const originalGoogleOnlyBeta = process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY;
    let googleCallback: GoogleCallback;

    beforeAll(() => {
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { assign: assignMock },
        });

        class ResizeObserverMock {
            constructor(private callback: ResizeObserverCallback) {}

            observe() {
                this.callback(
                    [{ contentRect: { width: 360 } } as ResizeObserverEntry],
                    this as unknown as ResizeObserver,
                );
            }

            disconnect() {}
            unobserve() {}
        }

        vi.stubGlobal('ResizeObserver', ResizeObserverMock);
        vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
            callback(0);
            return 1;
        });
    });

    beforeEach(() => {
        vi.clearAllMocks();
        process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID = '04d-client-id.apps.googleusercontent.com';
        process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY = 'false';
        initializeMock.mockImplementation((config: Record<string, unknown>) => {
            googleCallback = config.callback as GoogleCallback;
        });

        Object.defineProperty(window, 'google', {
            configurable: true,
            value: {
                accounts: {
                    id: {
                        initialize: initializeMock,
                        renderButton: renderButtonMock,
                        prompt: vi.fn(),
                    },
                },
            },
        });

        document.getElementById('gsi-script')?.remove();
        const script = document.createElement('script');
        script.id = 'gsi-script';
        document.head.appendChild(script);
    });

    afterEach(() => {
        cleanup();
        document.getElementById('gsi-script')?.remove();
    });

    afterAll(() => {
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: originalLocation,
        });
        if (originalClientId === undefined) {
            delete process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID;
        } else {
            process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID = originalClientId;
        }
        if (originalGoogleOnlyBeta === undefined) {
            delete process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY;
        } else {
            process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY = originalGoogleOnlyBeta;
        }
        vi.unstubAllGlobals();
    });

    async function renderClientPage() {
        const { default: ClienteEntrarPage } = await import('@/app/(auth)/entrar/cliente/page');
        const rendered = render(<ClienteEntrarPage />);
        await waitFor(() => expect(initializeMock).toHaveBeenCalledTimes(1));
        return rendered;
    }

    it('renders only the dedicated copy, Google control, status area, and return link', async () => {
        const { container } = await renderClientPage();

        expect(screen.getByRole('heading', { name: 'Ingresar a Mi Rubro' })).toBeInTheDocument();
        expect(screen.getByText('Usá la cuenta de Google registrada cuando se creó tu comercio')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Continuar con Google' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Volver al ingreso habitual' })).toHaveAttribute('href', '/entrar');
        expect(screen.getAllByRole('link')).toHaveLength(1);

        expect(container.querySelector('form')).not.toBeInTheDocument();
        expect(container.querySelector('input')).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/email|usuario/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/contraseña/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/código.*negocio/i)).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /crear cuenta/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /^ingresar$/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /olvidaste|recuper/i })).not.toBeInTheDocument();
        expect(screen.queryByText(/ingreso interno|autoservicio/i)).not.toBeInTheDocument();
    });

    it('gets the GIS credential through the existing AuthForm and selects only the preauthorized login', async () => {
        googlePreauthorizedLoginMock.mockResolvedValueOnce({ success: false, message: 'Token de Google inválido' });
        await renderClientPage();

        await act(async () => {
            await googleCallback({ credential: 'credential-from-gis' });
        });

        expect(renderButtonMock).toHaveBeenCalledTimes(1);
        expect(googlePreauthorizedLoginMock).toHaveBeenCalledWith('credential-from-gis');
        expect(googleAuthMock).not.toHaveBeenCalled();
    });

    it.each([
        [{ success: true, onboarding: true }, '/app/onboarding'],
        [{ success: true, onboarding: false }, '/app/dashboard'],
    ])('accepts the cookie-backed success result and reuses the canonical redirect', async (result, destination) => {
        googlePreauthorizedLoginMock.mockResolvedValueOnce(result);
        await renderClientPage();

        await act(async () => {
            await googleCallback({ credential: 'authorized-owner' });
        });

        expect(assignMock).toHaveBeenCalledWith(destination);
    });

    it('shows the generic authorization rejection and never falls back or redirects', async () => {
        googlePreauthorizedLoginMock.mockResolvedValueOnce({
            success: false,
            code: 'google_account_not_authorized',
            message: 'Esta cuenta de Google no tiene un acceso habilitado. Verificá que estés usando el correo registrado por el administrador.',
        });
        await renderClientPage();

        await act(async () => {
            await googleCallback({ credential: 'unknown-owner' });
        });

        expect(screen.getByRole('alert')).toHaveTextContent(
            'Esta cuenta de Google no tiene un acceso habilitado. Verificá que estés usando el correo registrado por el administrador.',
        );
        expect(googleAuthMock).not.toHaveBeenCalled();
        expect(assignMock).not.toHaveBeenCalled();
    });

    it('disables the visible button and ignores duplicate GIS responses while a request is pending', async () => {
        let resolveLogin!: (result: { success: boolean; message?: string }) => void;
        googlePreauthorizedLoginMock.mockReturnValueOnce(new Promise((resolve) => {
            resolveLogin = resolve;
        }));
        await renderClientPage();

        let firstRequest!: Promise<void>;
        act(() => {
            firstRequest = googleCallback({ credential: 'first-credential' });
            void googleCallback({ credential: 'duplicate-credential' });
        });

        expect(screen.getByRole('button', { name: 'Ingresando...' })).toBeDisabled();
        expect(googlePreauthorizedLoginMock).toHaveBeenCalledTimes(1);

        await act(async () => {
            resolveLogin({ success: false, message: 'Token de Google inválido' });
            await firstRequest;
        });

        expect(screen.getByRole('button', { name: 'Continuar con Google' })).toBeEnabled();
    });

    it.each([
        'Token de Google inválido',
        'Error de red al autenticar con Google',
    ])('presents canonical Google errors: %s', async (message) => {
        googlePreauthorizedLoginMock.mockResolvedValueOnce({ success: false, message });
        await renderClientPage();

        await act(async () => {
            await googleCallback({ credential: 'failed-credential' });
        });

        expect(screen.getByRole('alert')).toHaveTextContent(message);
        expect(screen.getByRole('button', { name: 'Continuar con Google' })).toBeEnabled();
    });

    it('keeps /entrar fully self-service and on standard Google auth', async () => {
        googleAuthMock.mockResolvedValueOnce({ success: false, message: 'Expected test stop' });
        const { default: EntrarPage } = await import('@/app/(auth)/entrar/page');
        render(<EntrarPage />);
        await waitFor(() => expect(initializeMock).toHaveBeenCalledTimes(1));

        expect(screen.getByLabelText('Email o usuario')).toHaveAttribute('name', 'email');
        expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password');
        expect(screen.getAllByRole('button', { name: 'Ingresar' })).toHaveLength(2);
        expect(screen.getByRole('button', { name: 'Crear cuenta' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' }))
            .toHaveAttribute('href', '/olvidar-contrasena');
        expect(screen.getByRole('button', { name: 'Continuar con Google' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: '¿Tu cuenta fue creada por Mi Rubro? Ingresá como cliente' }))
            .toHaveAttribute('href', '/entrar/cliente');

        await act(async () => {
            await googleCallback({ credential: 'self-service-credential' });
        });

        expect(googleAuthMock).toHaveBeenCalledWith('self-service-credential');
        expect(googlePreauthorizedLoginMock).not.toHaveBeenCalled();
    });

    it('keeps AuthForm defaults on the traditional form and standard Google endpoint', async () => {
        googleAuthMock.mockResolvedValueOnce({ success: false, message: 'Expected test stop' });
        const { AuthForm } = await import('@/components/auth/auth-form');
        render(<AuthForm />);
        await waitFor(() => expect(initializeMock).toHaveBeenCalledTimes(1));

        expect(screen.getByLabelText('Email o usuario')).toBeInTheDocument();
        expect(screen.getByLabelText('Contraseña')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Crear cuenta' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' })).toBeInTheDocument();

        await act(async () => {
            await googleCallback({ credential: 'default-auth-form-credential' });
        });

        expect(googleAuthMock).toHaveBeenCalledWith('default-auth-form-credential');
        expect(googlePreauthorizedLoginMock).not.toHaveBeenCalled();
    });

    it('does not write Google credentials or tokens to persistent browser state', async () => {
        const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');
        googlePreauthorizedLoginMock.mockResolvedValueOnce({ success: true, onboarding: false });
        await renderClientPage();

        await act(async () => {
            await googleCallback({ credential: 'never-persist-this' });
        });

        expect(storageSetItem).not.toHaveBeenCalled();
    });
});
