// ── Tenant support ticket types ─────────────────────────────────────────────
// Shapes match the backend tenant serialisation (tenant_support_views.py).

export type TenantTicketRow = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  category: string;
  created_at: string | null;
  updated_at: string | null;
  has_staff_reply: boolean;
  last_reply_at: string | null;
};

export type TenantTicketList = {
  results: TenantTicketRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type TenantTicketMessage = {
  id: string;
  body: string;
  created_at: string | null;
  is_from_staff: boolean;
  author_name: string;
};

export type TenantTicketDetail = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  category: string;
  created_at: string | null;
  updated_at: string | null;
  messages: TenantTicketMessage[];
  can_close: boolean;
  can_reopen: boolean;
};

export type TenantTicketCreateResponse = {
  id: string;
  reference: string;
};
