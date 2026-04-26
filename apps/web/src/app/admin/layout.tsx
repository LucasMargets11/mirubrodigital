import { ReactNode } from 'react';
import { redirect } from 'next/navigation';
import { headers } from 'next/headers';

import { getSession } from '@/lib/auth';
import { getAdminSession } from '@/lib/admin';
import { AdminShell } from '@/components/admin/admin-shell';
import { AdminForbidden } from '@/components/admin/admin-forbidden';

/**
 * /admin layout — protects the entire admin panel (except login/mfa-setup).
 *
 * Public paths that skip auth gate:
 *  - /admin/login      → admin login form (credentials + MFA)
 *  - /admin/mfa-setup  → initial TOTP enrollment after bootstrap login
 *
 * All other /admin/* paths require:
 *  1. Authenticated session (JWT cookies)
 *  2. Platform staff status (is_platform_staff=true)
 */
const PUBLIC_PATHS = ['/admin/login', '/admin/mfa-setup'];

export default async function AdminLayout({ children }: { children: ReactNode }) {
  // Detect current path via x-pathname set by middleware.ts
  const headersList = await headers();
  const pathname = headersList.get('x-pathname') ?? '';

  // Public admin pages (login, mfa-setup) skip auth gate
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return <>{children}</>;
  }

  // 1. Check basic authentication
  const session = await getSession();
  if (!session) {
    redirect('/admin/login');
  }

  // 2. Check platform staff access
  const adminSession = await getAdminSession();
  if (!adminSession) {
    return <AdminForbidden />;
  }

  return <AdminShell session={adminSession}>{children}</AdminShell>;
}
