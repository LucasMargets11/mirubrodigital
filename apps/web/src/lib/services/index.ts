const SERVICE_ENTRY_ROUTES: Record<string, string> = {
    gestion: '/app/gestion/dashboard',
    restaurante: '/app/orders',
    menu_qr: '/app/menu',
};

export function getServiceEntryPath(slug: string): string | undefined {
    return SERVICE_ENTRY_ROUTES[slug];
}
