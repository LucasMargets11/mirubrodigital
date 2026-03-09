'use client';

/**
 * /pos/terminal/new-sale — Full-screen POS sale creation page.
 *
 * Thin shell: auth guard happens in the parent /pos layout (EmployeeSessionProvider +
 * PosGuard). This page just renders the PosNewSalePage component.
 */

import { PosNewSalePage } from '@/features/pos/components/PosNewSalePage';

export default function PosNewSaleRoute() {
  return <PosNewSalePage />;
}
