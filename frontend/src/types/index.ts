// ── Auth ─────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  is_active: boolean;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

// ── Products ─────────────────────────────────────────────────────────
export interface Product {
  id: string;
  external_id?: string;
  supplier_code?: string;
  integration_id?: string;
  source?: string;
  name: string;
  description: string;
  category: string;
  sku: string;
  base_price: number;
  sell_price: number;
  sell_price_ron?: number;
  currency: string;
  min_quantity: number;
  image_url: string;
  images?: string[];
  color_names?: string[];
  colors?: { name: string; hex: string; image?: string }[];
  material: string;
  size: string;
  print_area: string;
  stock: number;
  brand?: string;
  price_range?: string;
  customizable?: boolean;
  variant_colors?: { name: string; hex: string; image?: string }[];
  total_stock?: number;
  variant_count?: number;
  min_sell_price?: number | null;
  max_sell_price?: number | null;
  supplier_margin?: number;
  effective_margin?: number;
  created_at?: string;
  _formatted?: Record<string, string>;
}

export interface SearchFacets {
  category?: Record<string, number>;
  subcategory?: Record<string, number>;
  price_range?: Record<string, number>;
  color_names?: Record<string, number>;
  color_groups?: Record<string, number>;
  brand?: Record<string, number>;
  source?: Record<string, number>;
}

export interface SearchResponse {
  results: Product[];
  total: number;
  page: number;
  total_pages: number;
  query: string;
  processing_time_ms: number;
  facets: SearchFacets;
  color_hex_map?: Record<string, string>;
}

export interface SearchFilters {
  q?: string;
  category?: string;
  subcategory?: string;
  category_group?: string;
  unified_category?: string;
  unified_subcategory?: string;
  min_price?: number;
  max_price?: number;
  color?: string;
  color_group?: string;
  integration_id?: string;
  in_stock?: boolean;
  sort?: string;
  page?: number;
  limit?: number;
  group_variants?: boolean;
}

export type UnifiedTree = Record<string, Record<string, number>>;

export interface ProductVariant {
  id: string;
  external_id: string;
  supplier_code: string;
  name: string;
  description: string;
  short_description: string;
  category: string;
  subcategory: string;
  brand: string;
  base_price: number;
  sell_price: number;
  sell_price_ron: number;
  currency: string;
  primary_image: string;
  images: string[];
  color: { name: string; hex: string; image?: string };
  colors: { name: string; hex: string; image?: string }[];
  specifications: Record<string, string>;
  printing_options: unknown[];
  stock: number;
  min_order_qty: number;
}

export interface VariantsResponse {
  supplier_code: string;
  name: string;
  category: string;
  brand: string;
  total_stock: number;
  variant_count: number;
  variants: ProductVariant[];
}

export interface QuoteItem {
  id?: string;
  product_id?: string;
  product_name: string;
  product_sku: string;
  product_color?: string;
  product_size?: string;
  product_image?: string;
  size_prices?: { size: string; price: number }[];
  size_quantities?: { size: string; qty: number }[];
  quantity: number;
  unit_price: number;
  margin_percent: number;
  sell_price: number;
  total: number;
  printing_method?: string;
  printing_cost?: number;
  printing_setup?: number;
  customization_notes?: string;
  notes: string;
  is_confirmed?: boolean;
}

export interface Quote {
  id: string | number;
  number: string;
  company_id?: string | null;
  company_name?: string | null;
  client_name: string;
  client_email: string;
  client_company: string;
  client_phone?: string;
  status: string;
  notes: string;
  subtotal: number;
  margin_percent: number;
  total: number;
  currency: string;
  items: QuoteItem[];
  created_at?: string;
  updated_at?: string;
}

export interface Company {
  id: string;
  name: string;
  cui: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  bank: string;
  iban: string;
  logo_url: string;
  is_default: boolean;
  created_at?: string;
}

export interface Integration {
  id: string;
  name: string;
  display_name: string;
  integration_type: string;
  api_url: string;
  api_key: string;
  api_user: string;
  api_password: string;
  extra_config: Record<string, unknown>;
  default_margin: number;
  sync_frequency: string;
  is_active: boolean;
  last_sync_at?: string;
  last_sync_status: string;
  last_sync_error: string;
  last_sync_duration: number;
  products_count: number;
  created_at?: string;
}

export interface IntegrationCreate {
  name: string;
  display_name: string;
  integration_type: string;
  api_url?: string;
  api_key?: string;
  api_user?: string;
  api_password?: string;
  extra_config?: Record<string, unknown>;
  default_margin?: number;
  sync_frequency?: string;
  is_active?: boolean;
}

export interface SyncProgress {
  stage: string;
  current: number;
  total: number;
  percent: number;
  message: string;
}

export interface AppSetting {
  key: string;
  value: string;
  value_type: string;
  description: string;
  group_name: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  products?: Product[];
  timestamp: Date;
}

export interface ChatStreamEvent {
  type: "text" | "products" | "quote_update" | "action" | "done";
  content: string | Product[] | Record<string, unknown>;
}

export interface CategoryCount {
  name: string;
  count: number;
}

/** 3-level tree: supplier → group → { subcategory: count } */
export type CategoryTree = Record<string, Record<string, Record<string, number>>>;
