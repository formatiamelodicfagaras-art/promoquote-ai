import type {
  Product,
  Quote,
  Company,
  Integration,
  IntegrationCreate,
  SyncProgress,
  AppSetting,
  ChatStreamEvent,
  SearchResponse,
  SearchFilters,
  CategoryCount,
  VariantsResponse,
  User,
} from "@/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

// ── Auth helpers ─────────────────────────────────────────────────────
function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("sq-token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return headers;
}

/** Wrapper around fetch that auto-injects the auth token */
async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const existing = (init?.headers as Record<string, string>) ?? {};
  return fetch(input, {
    ...init,
    headers: authHeaders(existing),
  });
}

// ── Auth API ─────────────────────────────────────────────────────────
export async function login(
  email: string,
  password: string
): Promise<{ token: string; user: User }> {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Invalid credentials");
  }
  const data = await res.json();
  return { token: data.access_token, user: data.user };
}

export async function fetchMe(): Promise<User> {
  const res = await authFetch(`${API}/auth/me`);
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

export async function updateProfile(
  data: { name?: string; email?: string; password?: string }
): Promise<User> {
  const res = await authFetch(`${API}/auth/me`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update profile");
  return res.json();
}

export async function fetchUsers(): Promise<User[]> {
  const res = await authFetch(`${API}/users/`);
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function createUser(
  data: { name: string; email: string; password: string; is_admin?: boolean }
): Promise<User> {
  const res = await authFetch(`${API}/users/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "Failed to create user");
  }
  return res.json();
}

export async function updateUser(
  id: string,
  data: { name?: string; email?: string; password?: string; is_admin?: boolean; is_active?: boolean }
): Promise<User> {
  const res = await authFetch(`${API}/users/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update user");
  return res.json();
}

export async function deleteUser(id: string): Promise<void> {
  const res = await authFetch(`${API}/users/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete user");
}

// ── Products / Search ────────────────────────────────────────────────
export async function searchProducts(
  filters: SearchFilters
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.category) params.set("category", filters.category);
  if (filters.subcategory) params.set("subcategory", filters.subcategory);
  if (filters.category_group) params.set("category_group", filters.category_group);
  if (filters.unified_category) params.set("unified_category", filters.unified_category);
  if (filters.unified_subcategory) params.set("unified_subcategory", filters.unified_subcategory);
  if (filters.min_price != null)
    params.set("min_price", String(filters.min_price));
  if (filters.max_price != null)
    params.set("max_price", String(filters.max_price));
  if (filters.color) params.set("color", filters.color);
  if (filters.color_group) params.set("color_group", filters.color_group);
  if (filters.integration_id)
    params.set("integration_id", filters.integration_id);
  if (filters.in_stock) params.set("in_stock", "true");
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.group_variants !== undefined)
    params.set("group_variants", String(filters.group_variants));

  const res = await authFetch(`${API}/products/search?${params}`);
  if (!res.ok) throw new Error("Failed to search products");
  return res.json();
}

export interface SuggestionItem {
  name: string;
  code: string;
  category: string;
  image?: string;
  highlighted_name?: string;
  highlighted_code?: string;
}

export async function getSuggestions(
  query: string,
  limit = 10
): Promise<SuggestionItem[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await authFetch(`${API}/products/suggest?${params}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.suggestions ?? [];
}

export async function getCategories(): Promise<CategoryCount[]> {
  const res = await authFetch(`${API}/products/categories`);
  if (!res.ok) throw new Error("Failed to fetch categories");
  return res.json();
}

/** 3-level tree: supplier → group → { subcategory: count } */
export type CategoryTree = Record<string, Record<string, Record<string, number>>>;

export async function getCategoryTree(): Promise<CategoryTree> {
  const res = await authFetch(`${API}/products/category-tree`);
  if (!res.ok) throw new Error("Failed to fetch category tree");
  return res.json();
}

export async function getUnifiedTree(): Promise<Record<string, Record<string, number>>> {
  const res = await authFetch(`${API}/products/unified-tree`);
  if (!res.ok) throw new Error("Failed to fetch unified tree");
  return res.json();
}

export async function getProduct(id: string): Promise<Product> {
  const res = await authFetch(`${API}/products/${id}`);
  if (!res.ok) throw new Error("Failed to fetch product");
  return res.json();
}

export async function getProductVariants(
  supplierCode: string,
  integrationId?: string
): Promise<VariantsResponse> {
  const params = integrationId
    ? `?integration_id=${encodeURIComponent(integrationId)}`
    : "";
  const res = await authFetch(
    `${API}/products/variants/${encodeURIComponent(supplierCode)}${params}`
  );
  if (!res.ok) throw new Error("Failed to fetch variants");
  return res.json();
}

// ── Quotes ────────────────────────────────────────────────────────────
export async function fetchQuotes(): Promise<Quote[]> {
  const res = await authFetch(`${API}/quotes/`);
  if (!res.ok) throw new Error("Failed to fetch quotes");
  return res.json();
}

export interface ClientSuggestion {
  client_name: string;
  client_company: string;
  client_email: string;
}

export async function fetchClientSuggestions(
  q?: string,
  limit = 20,
): Promise<ClientSuggestion[]> {
  const params = new URLSearchParams();
  if (q && q.trim()) params.set("q", q.trim());
  params.set("limit", String(limit));
  const res = await authFetch(`${API}/quotes/clients?${params.toString()}`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchQuote(id: string | number): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${id}`);
  if (!res.ok) throw new Error("Failed to fetch quote");
  return res.json();
}

export async function createQuote(data: Partial<Quote>): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create quote");
  }
  return res.json();
}

export async function updateQuote(
  quoteId: number | string,
  data: { number?: string; company_id?: string | null; client_name?: string; client_company?: string; client_email?: string; client_phone?: string }
): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update quote");
  return res.json();
}

export async function addQuoteItem(
  quoteId: number | string,
  item: {
    product_id?: string;
    product_name: string;
    product_sku?: string;
    product_color?: string;
    product_image?: string;
    product_size?: string;
    quantity: number;
    unit_price: number;
    margin_percent: number;
    printing_method?: string;
    printing_cost?: number;
    printing_setup?: number;
    customization_notes?: string;
    size_quantities?: { size: string; qty: number }[];
  }
): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error("Failed to add item");
  return res.json();
}

export async function updateQuoteItem(
  quoteId: number | string,
  itemId: number | string,
  data: { quantity?: number; product_color?: string; product_size?: string; printing_method?: string; printing_cost?: number; printing_setup?: number; customization_notes?: string; notes?: string }
): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update item");
  return res.json();
}

export async function removeQuoteItem(
  quoteId: number | string,
  itemId: number | string
): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}/items/${itemId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to remove item");
  return res.json();
}

export async function deleteQuote(quoteId: number | string): Promise<void> {
  const res = await authFetch(`${API}/quotes/${quoteId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete quote");
}

export async function confirmQuote(
  quoteId: number | string,
  confirmedItemIds?: string[]
): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}/confirm`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_items: confirmedItemIds || [] }),
  });
  if (!res.ok) throw new Error("Failed to confirm quote");
  return res.json();
}

export async function unconfirmQuote(quoteId: number | string): Promise<Quote> {
  const res = await authFetch(`${API}/quotes/${quoteId}/unconfirm`, { method: "PUT" });
  if (!res.ok) throw new Error("Failed to unconfirm quote");
  return res.json();
}

export async function generatePDF(quoteId: number): Promise<Blob> {
  const res = await authFetch(`${API}/quotes/${quoteId}/pdf`);
  if (!res.ok) throw new Error("Failed to generate PDF");
  return res.blob();
}

export async function generateInternalPDF(quoteId: number | string): Promise<Blob> {
  const res = await authFetch(`${API}/quotes/${quoteId}/internal-pdf`);
  if (!res.ok) throw new Error("Failed to generate internal PDF");
  return res.blob();
}

// ── Integrations ──────────────────────────────────────────────────────
export async function fetchIntegrations(): Promise<Integration[]> {
  const res = await authFetch(`${API}/integrations/`);
  if (!res.ok) throw new Error("Failed to fetch integrations");
  return res.json();
}

export async function createIntegration(
  data: IntegrationCreate
): Promise<Integration> {
  const res = await authFetch(`${API}/integrations/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create integration");
  return res.json();
}

export async function updateIntegration(
  id: string,
  data: Partial<Integration>
): Promise<Integration> {
  const res = await authFetch(`${API}/integrations/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update integration");
  return res.json();
}

export async function deleteIntegration(id: string): Promise<void> {
  const res = await authFetch(`${API}/integrations/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete integration");
}

export async function triggerSync(id: string): Promise<void> {
  const res = await authFetch(`${API}/integrations/${id}/sync`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Failed to trigger sync");
  }
}

export function subscribeSyncProgress(
  integrationId: string,
  onProgress: (progress: SyncProgress) => void
): () => void {
  const es = new EventSource(`${API}/integrations/${integrationId}/sync/status`);
  es.addEventListener("progress", (event) => {
    try {
      const data = JSON.parse(event.data) as SyncProgress;
      onProgress(data);
    } catch {
      // skip malformed
    }
  });
  es.onerror = () => es.close();
  return () => es.close();
}

// ── Companies ─────────────────────────────────────────────────────────
export async function fetchCompanies(): Promise<Company[]> {
  const res = await authFetch(`${API}/companies/`);
  if (!res.ok) throw new Error("Failed to fetch companies");
  return res.json();
}

export async function createCompany(
  data: Omit<Company, "id" | "created_at">
): Promise<Company> {
  const res = await authFetch(`${API}/companies/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create company");
  return res.json();
}

export async function updateCompany(
  id: string,
  data: Partial<Company>
): Promise<Company> {
  const res = await authFetch(`${API}/companies/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update company");
  return res.json();
}

export async function deleteCompany(id: string): Promise<void> {
  const res = await authFetch(`${API}/companies/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete company");
}

export async function setDefaultCompany(id: string): Promise<Company> {
  const res = await authFetch(`${API}/companies/${id}/set-default`, {
    method: "PUT",
  });
  if (!res.ok) throw new Error("Failed to set default company");
  return res.json();
}

// ── Settings ──────────────────────────────────────────────────────────
export async function fetchSettings(): Promise<AppSetting[]> {
  const res = await authFetch(`${API}/settings/`);
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function updateSetting(
  key: string,
  value: string
): Promise<AppSetting> {
  const res = await authFetch(`${API}/settings/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error("Failed to update setting");
  return res.json();
}

export async function batchUpdateSettings(
  settings: Record<string, string>
): Promise<void> {
  const res = await authFetch(`${API}/settings/batch/update`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  });
  if (!res.ok) throw new Error("Failed to update settings");
}

export async function getCategoryMargins(): Promise<Record<string, number>> {
  const res = await authFetch(`${API}/settings/margins/categories`);
  if (!res.ok) return {};
  const data = await res.json();
  return data.margins ?? {};
}

export async function updateCategoryMargins(
  margins: Record<string, number>
): Promise<void> {
  const res = await authFetch(`${API}/settings/margins/categories`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(margins),
  });
  if (!res.ok) throw new Error("Failed to update margins");
}

// ── Chat (SSE streaming) ─────────────────────────────────────────────
export async function sendChatMessage(
  message: string,
  history: { role: string; content: string }[],
  quoteId: number | null,
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
  const res = await authFetch(`${API}/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_history: history,
      quote_id: quoteId,
    }),
  });

  if (!res.ok) throw new Error("Chat request failed");

  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as ChatStreamEvent;
          onEvent(event);
        } catch {
          // skip malformed events
        }
      }
    }
  }
}
