export type BillingVertical = 'commercial' | 'restaurant' | 'menu_qr';

export interface Module {
  code: string;
  name: string;
  description: string;
  category: 'operation' | 'admin' | 'insights';
  vertical: BillingVertical | 'both';
  price_monthly: number;
  price_yearly: number | null;
  is_core: boolean;
  requires: { code: string }[];
}

export interface Bundle {
  code: string;
  name: string;
  description: string;
  vertical: BillingVertical;
  badge?: string;
  modules: Module[];
  pricing_mode: 'fixed_price' | 'discount_percent';
  fixed_price_monthly: number | null;
  fixed_price_yearly: number | null;
  discount_percent: string | null; // Decimal comes as string often
  is_default_recommended: boolean;
}

export interface QuoteRequest {
  vertical: BillingVertical;
  billing_period: 'monthly' | 'yearly';
  plan_type: 'bundle' | 'custom';
  selected_module_codes?: string[];
  bundle_code?: string;
}

export interface QuoteResponse {
  subtotal: number;
  bundle_discount: number;
  promo_discount: number;
  total: number;
  modules: { code: string; name: string; price: number }[];
  suggestion?: {
    bundle_code: string;
    bundle_name: string;
    bundle_total: number;
    savings_amount: number;
    savings_percent: number;
  };
  applied_promo?: {
    code: string;
    name: string;
    amount: number;
  };
  currency: string;
}
