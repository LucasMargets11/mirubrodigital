import { describe, expect, it } from 'vitest';

import { isPathRestrictedForService, pathMatches } from '../service-path-gating';

// Slice 7C: `/app` en el allowlist + `startsWith` dejaba pasar cualquier
// `/app/*`. La raíz matchea solo exacto; las rutas de módulo sí admiten subrutas.

const COMMON_ALLOWED = [
    '/app',
    '/app/servicios',
    '/app/planes',
    '/app/settings',
    '/app/soporte',
    '/app/soporte/nuevo',
    '/app/cuenta/estado',
    '/app/dashboard',
];

function allowed(service: string, pathname: string) {
    return !isPathRestrictedForService(service, pathname);
}

describe('pathMatches', () => {
    it('la raíz /app matchea solo exacto', () => {
        expect(pathMatches('/app', '/app')).toBe(true);
        expect(pathMatches('/app/carta', '/app')).toBe(false);
        expect(pathMatches('/app/turnos', '/app')).toBe(false);
    });

    it('una ruta de módulo admite subrutas, sin falsos prefijos', () => {
        expect(pathMatches('/app/turnos', '/app/turnos')).toBe(true);
        expect(pathMatches('/app/turnos/turnos', '/app/turnos')).toBe(true);
        expect(pathMatches('/app/turnosx', '/app/turnos')).toBe(false);
    });
});

describe('appointments (solo Turnos)', () => {
    it.each([
        ...COMMON_ALLOWED,
        '/app/turnos',
        '/app/turnos/turnos',
        '/app/turnos/servicios/categorias',
        '/app/turnos/configuracion',
        // CUSTOMER 02: Clientes core compartido.
        '/app/clientes',
        '/app/clientes/0b7c1c55-0000-4000-8000-000000000000',
    ])(
        'permite %s',
        (path) => expect(allowed('appointments', path)).toBe(true),
    );

    it.each(['/app/carta', '/app/carta/publicacion', '/app/resenas', '/app/resenas/qr', '/app/gestion/dashboard', '/app/gestion/ventas', '/app/resto', '/app/orders', '/app/menu', '/app/clientesx'])(
        'bloquea %s',
        (path) => expect(allowed('appointments', path)).toBe(false),
    );
});

describe('menu_qr (solo Carta)', () => {
    it.each([...COMMON_ALLOWED, '/app/carta', '/app/carta/engagement', '/app/menu', '/app/settings/online-menu'])(
        'permite %s',
        (path) => expect(allowed('menu_qr', path)).toBe(true),
    );

    it.each(['/app/turnos', '/app/turnos/turnos', '/app/resenas', '/app/resenas/feedback', '/app/gestion/productos', '/app/tables'])(
        'bloquea %s',
        (path) => expect(allowed('menu_qr', path)).toBe(false),
    );
});

describe('qr_reviews (solo Reseñas)', () => {
    it.each([...COMMON_ALLOWED, '/app/resenas', '/app/resenas/analytics', '/app/settings/access'])(
        'permite %s',
        (path) => expect(allowed('qr_reviews', path)).toBe(true),
    );

    it.each(['/app/turnos', '/app/turnos/horarios', '/app/carta', '/app/carta/productos', '/app/gestion/ventas', '/app/kitchen'])(
        'bloquea %s',
        (path) => expect(allowed('qr_reviews', path)).toBe(false),
    );
});

describe('productos completos (gestion/restaurante)', () => {
    it.each(['gestion', 'restaurante'])('%s no se restringe', (service) => {
        expect(allowed(service, '/app/gestion/dashboard')).toBe(true);
        expect(allowed(service, '/app/carta')).toBe(true);
    });
});
