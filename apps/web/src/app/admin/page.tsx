import { redirect } from 'next/navigation';
import type { RedirectType } from 'next/navigation';

/**
 * /admin → redirects to /admin/dashboard
 */
export default function AdminIndexPage() {
  // @ts-expect-error -- /admin/dashboard is a valid route created in this module
  redirect('/admin/dashboard');
}
