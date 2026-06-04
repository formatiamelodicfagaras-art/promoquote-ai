import type { BrandKitProduct, MockupConfig } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export interface BrandKitSearchResult {
  results: BrandKitProduct[];
  total: number;
  page: number;
  total_pages: number;
  facets: Record<string, Record<string, number>>;
}

export interface ColorStat {
  color_group: string;
  product_count: number;
}

export async function searchBrandKitProducts(params: {
  colors?: string[];
  category?: string;
  categoryGroup?: string;
  minStock?: number;
  page?: number;
  limit?: number;
}): Promise<BrandKitSearchResult> {
  const sp = new URLSearchParams();
  if (params.colors?.length) sp.set("colors", params.colors.join(","));
  if (params.category) sp.set("category", params.category);
  if (params.categoryGroup) sp.set("category_group", params.categoryGroup);
  if (params.minStock) sp.set("min_stock", String(params.minStock));
  sp.set("page", String(params.page || 1));
  sp.set("limit", String(params.limit || 40));

  const res = await fetch(`${API}/brand-kit/products?${sp}`);
  if (!res.ok) throw new Error("Failed to search products");
  return res.json();
}

export async function getColorStats(): Promise<ColorStat[]> {
  const res = await fetch(`${API}/brand-kit/colors`);
  if (!res.ok) throw new Error("Failed to fetch colors");
  return res.json();
}

export async function uploadLogo(file: File): Promise<{ path: string; filename: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API}/brand-kit/upload-logo`, { method: "POST", body: fd });
  if (!res.ok) throw new Error("Failed to upload logo");
  return res.json();
}

export function getLogoUrl(filename: string): string {
  return `${API}/brand-kit/logo/${filename}`;
}

export async function getMockupZone(sku: string, supplier?: string): Promise<MockupConfig | null> {
  const sp = new URLSearchParams();
  if (supplier) sp.set("supplier", supplier);
  const res = await fetch(`${API}/brand-kit/mockup-zone/${sku}?${sp}`);
  if (!res.ok) return null;
  return res.json();
}

export async function saveMockupZone(sku: string, data: MockupConfig & { product_sku: string; supplier: string }): Promise<void> {
  await fetch(`${API}/brand-kit/mockup-zone/${sku}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function generatePdf(data: {
  client_name: string;
  company_id?: string;
  selected_products: Array<{
    sku: string;
    supplier: string;
    name: string;
    mockup_base64: string;
    image_url?: string;
    colors?: string[];
    print_method?: string;
    print_area?: string;
    print_dimensions?: string;
    min_order?: number;
  }>;
  logo_base64?: string;
}): Promise<{ pdf_url: string; brand_kit_id: string }> {
  const res = await fetch(`${API}/brand-kit/generate-pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to generate PDF");
  return res.json();
}

export async function saveBrandKit(data: {
  name: string;
  client_name: string;
  logo_path: string;
  colors: string[];
  selected_products: Array<Record<string, unknown>>;
  mockup_overrides: Record<string, MockupConfig>;
}): Promise<{ id: string }> {
  const res = await fetch(`${API}/brand-kit/saved`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to save brand kit");
  return res.json();
}

export async function listBrandKits(): Promise<Array<{
  id: string;
  name: string;
  client_name: string;
  product_count: number;
  created_at: string;
}>> {
  const res = await fetch(`${API}/brand-kit/saved`);
  if (!res.ok) throw new Error("Failed to list brand kits");
  return res.json();
}

export async function deleteBrandKit(id: string): Promise<void> {
  await fetch(`${API}/brand-kit/saved/${id}`, { method: "DELETE" });
}

// ── PACKMAN AI Chat (SSE) ──────────────────────────

export interface PackmanChatEvent {
  type: "text" | "products" | "tool_call" | "error" | "done";
  content: string | BrandKitProduct[] | Record<string, unknown>;
}

export async function sendPackmanMessage(
  message: string,
  history: { role: string; content: string }[],
  brandColors: string[],
  onEvent: (event: PackmanChatEvent) => void,
): Promise<void> {
  const res = await fetch(`${API}/brand-kit/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_history: history,
      brand_colors: brandColors,
    }),
  });

  if (!res.ok) throw new Error("PACKMAN chat request failed");

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
      const trimmed = line.trim();
      if (!trimmed) continue;

      const dataStr = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
      if (!dataStr) continue;

      try {
        const event = JSON.parse(dataStr) as PackmanChatEvent;
        onEvent(event);
      } catch {
        // ignore malformed lines
      }
    }
  }
}
