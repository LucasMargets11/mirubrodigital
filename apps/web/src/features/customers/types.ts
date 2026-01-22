export type CustomerSummary = {
    id: string;
    name: string;
    doc_type: string | null;
    doc_number: string | null;
    email: string | null;
    phone: string | null;
};

export type Customer = CustomerSummary & {
    type: 'individual' | 'company';
    tax_condition: string | null;
    address_line: string | null;
    city: string | null;
    province: string | null;
    postal_code: string | null;
    country: string | null;
    note: string | null;
    tags: string[];
    is_active: boolean;
    created_at: string;
    updated_at: string;
};

export type CustomerPayload = {
    name: string;
    type?: Customer['type'];
    doc_type?: string;
    doc_number?: string;
    tax_condition?: string;
    email?: string;
    phone?: string;
    address_line?: string;
    city?: string;
    province?: string;
    postal_code?: string;
    country?: string;
    note?: string;
    is_active?: boolean;
};

export type CustomerFilters = {
    search?: string;
    includeInactive?: boolean;
    limit?: number;
    offset?: number;
};
