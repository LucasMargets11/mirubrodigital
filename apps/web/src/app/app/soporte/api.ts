import { serverApiFetch } from '@/lib/api/server';

import type { TenantTicketList, TenantTicketDetail } from './types';

export async function getTenantTickets(status?: string): Promise<TenantTicketList> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return serverApiFetch<TenantTicketList>(`/api/v1/support/tickets/${qs}`);
}

export async function getTenantTicketDetail(ticketId: string): Promise<TenantTicketDetail> {
  return serverApiFetch<TenantTicketDetail>(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}/`);
}
