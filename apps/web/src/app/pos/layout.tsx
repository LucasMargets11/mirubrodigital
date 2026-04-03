'use client';

/**
 * POS route group layout.
 *
 * - Wraps all /pos/* routes with EmployeeSessionProvider.
 * - Guards access: if no session → /pos/login
 *
 * This layout is a pure client component because it reads sessionStorage
 * and must react to session state changes.
 */

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { EmployeeSessionProvider, useEmployeeSession } from '@/features/pos/context';

function PosGuard({ children }: { children: React.ReactNode }) {
  const { session } = useEmployeeSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (session.status === 'loading') return;

    if (session.status === 'unauthenticated' || session.status === 'error') {
      if (pathname !== '/pos/login') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        router.replace('/pos/login' as any);
      }
      return;
    }
  }, [session, pathname, router]);

  // Show nothing while redirecting
  if (session.status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">Cargando sesión…</p>
      </div>
    );
  }

  // On /pos/login the guard should not block rendering even when unauthenticated
  if (
    (session.status === 'unauthenticated' || session.status === 'error') &&
    pathname !== '/pos/login'
  ) {
    return null;
  }

  return <>{children}</>;
}

export default function PosLayout({ children }: { children: React.ReactNode }) {
  return (
    <EmployeeSessionProvider>
      <PosGuard>{children}</PosGuard>
    </EmployeeSessionProvider>
  );
}
