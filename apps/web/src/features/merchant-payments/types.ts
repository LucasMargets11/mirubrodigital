/** Estado público de la conexión MP del Business (nunca incluye tokens). */
export type MercadoPagoConnectionStatus = {
    connected: boolean;
    status: 'connected' | 'expired' | 'revoked' | 'error' | null;
    mp_user_id: string | null;
    updated_at: string | null;
};

/**
 * Producto desde el que se inicia el OAuth. Valor cerrado: el backend lo guarda
 * asociado al `state` y decide a qué pantalla interna volver.
 */
export type MercadoPagoOAuthContext = 'menu' | 'appointments';
