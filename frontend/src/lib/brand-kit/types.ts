export interface PrintArea {
  location: string;
  width_mm: number;
  height_mm: number;
  method: string;
  position_image?: string;
}

export interface BrandKitProduct {
  id: string;
  sku: string;
  name: string;
  supplier: string;
  category: string;
  color: string;
  color_hex: string;
  stock: number;
  image_url: string;
  images: string[];
  min_order: number;
  print_areas: PrintArea[];
  brand?: string;
}

export type WarpMode = "none" | "cylinder" | "arc";

export interface MockupConfig {
  x_percent: number;
  y_percent: number;
  width_percent: number;
  height_percent: number;
  opacity: number;
  blend_mode: string;
  rotation: number;
  warp: WarpMode;
  warp_intensity: number; // 0-100
}

export interface MockupOverride extends MockupConfig {
  product_sku: string;
  supplier: string;
}

export interface BrandKit {
  id: string;
  name: string;
  client_name: string;
  logo_path: string;
  colors: string[];
  selected_products: BrandKitProduct[];
  mockup_overrides: Record<string, MockupConfig>;
  pdf_path?: string;
  created_at: string;
  updated_at: string;
}

export type UnifiedColor = keyof typeof import("./color-mapping").UNIFIED_COLORS;
