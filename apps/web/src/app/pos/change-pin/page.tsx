'use client';

/**
 * PIN change disabled — /pos/change-pin
 *
 * Self-service PIN change is disabled. PINs are managed exclusively
 * by the business owner/admin. This page shows an informational message.
 */

import Link from 'next/link';

export default function PosChangePinPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-md text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100">
          <svg
            className="h-6 w-6 text-amber-600"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
            />
          </svg>
        </div>

        <h1 className="mb-2 text-xl font-semibold text-gray-900">
          PIN administrado
        </h1>

        <p className="mb-6 text-sm text-gray-600">
          El PIN es administrado por el responsable del negocio.
          Contactalo para obtener un nuevo PIN.
        </p>

        <Link
          href="/pos/login"
          className="inline-block w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-blue-700"
        >
          Volver al inicio
        </Link>
      </div>
    </div>
  );
}
