import Link from 'next/link';
import { ShieldAlert } from 'lucide-react';

/**
 * Forbidden screen shown when a non-staff user tries to access /admin.
 * Self-contained — no AdminShell wrapping needed.
 */
export function AdminForbidden() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
          <ShieldAlert className="h-8 w-8 text-red-600" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-slate-900">Acceso restringido</h1>
          <p className="text-sm text-slate-500">
            Esta sección está reservada para el equipo interno de Mi Rubro.
            Si creés que deberías tener acceso, contactá al administrador de la plataforma.
          </p>
        </div>
        <div className="flex items-center justify-center gap-3">
          <Link
            href="/app/dashboard"
            className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
          >
            Ir al panel
          </Link>
          <Link
            href="/"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            Ir al inicio
          </Link>
        </div>
      </div>
    </div>
  );
}
