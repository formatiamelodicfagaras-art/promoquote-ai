import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Message, Quote, QuoteItem, Product } from "@/types";
import { createQuote, addQuoteItem, fetchSettings, getProductVariants } from "./api";
import type { BrandKitProduct } from "./brand-kit/types";

const _SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL",
                     "6XL", "7XL", "8XL", "9XL", "10XL"];
function _sizeIdx(s: string): number {
  const idx = _SIZE_ORDER.indexOf(s.toUpperCase());
  return idx < 0 ? 100 : idx;
}

/** Draft item held locally until PDF is generated */
export interface DraftItem {
  localId: string;
  product_id?: string;
  product_name: string;
  product_sku: string;
  product_color: string;
  product_size: string;
  product_image: string;
  quantity: number;
  unit_price: number;
  margin_percent: number;
  sell_price: number;
  printing_method: string;
  printing_cost: number;
  printing_setup: number;
  customization_notes: string;
  colors: { name: string; hex: string; image?: string }[];
  size_prices?: { size: string; price: number }[];
  size_quantities?: { size: string; qty: number }[];
}

interface AppStore {
  // Chat
  messages: Message[];
  isAiTyping: boolean;
  streamingContent: string;

  // Quote — can be a saved Quote (from DB) or draft items (local only)
  currentQuote: Quote | null;
  draftItems: DraftItem[];
  draftNumber: string;
  draftClientName: string;
  draftClientCompany: string;
  draftClientEmail: string;
  draftCompanyId: string;
  /** If set, this draft replaces an existing quote — delete the old one after PDF generation */
  editingQuoteId: string | number | null;
  isQuotePanelOpen: boolean;

  // Unified category filter (shared between Header menu and Products page)
  unifiedCategory: string;
  unifiedSubcategory: string;
  setUnifiedCategory: (cat: string, sub: string) => void;

  // Packman
  packmanProducts: BrandKitProduct[];

  // Actions - Chat
  addMessage: (msg: Omit<Message, "id" | "timestamp">) => void;
  updateLastAssistantMessage: (content: string) => void;
  setIsAiTyping: (typing: boolean) => void;
  setStreamingContent: (content: string) => void;
  appendStreamingContent: (chunk: string) => void;
  clearChat: () => void;

  // Actions - Quote
  setCurrentQuote: (quote: Quote | null) => void;
  toggleQuotePanel: () => void;
  addToQuote: (product: Product, quantity?: number) => Promise<void>;
  removeFromQuote: (itemIndex: number) => void;
  updateDraftItem: (localId: string, updates: Partial<DraftItem>) => void;
  setDraftNumber: (value: string) => void;
  setDraftClientName: (value: string) => void;
  setDraftClientCompany: (value: string) => void;
  setDraftClientEmail: (value: string) => void;
  setDraftCompanyId: (value: string) => void;
  setDraftClient: (field: string, value: string) => void;
  loadQuoteAsDraft: (quote: Quote) => void;
  duplicateQuoteAsDraft: (quote: Quote) => void;
  appendQuoteAsDraft: (quote: Quote) => void;
  clearDraft: () => void;

  // Actions - Packman
  addToPackman: (product: Product) => void;
  removeFromPackman: (id: string) => void;
  clearPackman: () => void;
}

const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;
let messageCounter = 0;

export const useStore = create<AppStore>()(persist((set, get) => ({
  messages: [],
  isAiTyping: false,
  streamingContent: "",
  currentQuote: null,
  draftItems: [],
  draftNumber: "",
  draftClientName: "",
  draftClientCompany: "",
  draftClientEmail: "",
  draftCompanyId: "",
  editingQuoteId: null,
  isQuotePanelOpen: false,
  unifiedCategory: "",
  unifiedSubcategory: "",
  setUnifiedCategory: (cat, sub) => set({ unifiedCategory: cat, unifiedSubcategory: sub }),
  packmanProducts: [],

  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...msg,
          id: `msg-${++messageCounter}-${Date.now()}`,
          timestamp: new Date(),
        },
      ],
    })),

  updateLastAssistantMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], content };
          break;
        }
      }
      return { messages: msgs };
    }),

  setIsAiTyping: (typing) => set({ isAiTyping: typing }),
  setStreamingContent: (content) => set({ streamingContent: content }),
  appendStreamingContent: (chunk) =>
    set((state) => ({ streamingContent: state.streamingContent + chunk })),
  clearChat: () =>
    set({ messages: [], streamingContent: "", isAiTyping: false }),

  setCurrentQuote: (quote) =>
    set({ currentQuote: quote, isQuotePanelOpen: quote !== null }),
  toggleQuotePanel: () =>
    set((state) => ({ isQuotePanelOpen: !state.isQuotePanelOpen })),

  addToQuote: async (product, quantity) => {
    try {
      // Fetch global margin from settings (default 30%)
      let globalMargin = 30;
      try {
        const settings = await fetchSettings();
        const marginSetting = settings.find((s) => s.key === "margin_percent");
        if (marginSetting) {
          const val = parseFloat(marginSetting.value);
          if (!isNaN(val)) globalMargin = val;
        }
      } catch {
        // fallback to 30%
      }

      const effectiveMargin = product.effective_margin ?? globalMargin;
      const colorName = product.color_names?.[0] || product.colors?.[0]?.name || "";
      const sizeName = product.size || "";
      const imgUrl = product.image_url || product.images?.[0] || "";
      const sellPrice = round(product.base_price * (1 + effectiveMargin / 100), 2);

      // For textile products (multiple size variants), fetch size-price breakdown
      let size_prices: { size: string; price: number }[] | undefined;
      if (product.supplier_code) {
        try {
          const vr = await getProductVariants(product.supplier_code, product.integration_id);
          const sizeMap = new Map<string, number>();
          for (const v of vr.variants || []) {
            const sz = v.specifications?.size || "";
            const p = v.base_price || 0;
            if (sz && p > 0 && !sizeMap.has(sz)) sizeMap.set(sz, p);
          }
          if (sizeMap.size > 1) {
            size_prices = Array.from(sizeMap.entries())
              .map(([size, price]) => ({ size, price: round(price, 4) }))
              .sort((a, b) => _sizeIdx(a.size) - _sizeIdx(b.size));
          }
        } catch {
          // Size breakdown is optional; ignore failures
        }
      }

      const draft: DraftItem = {
        localId: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        product_id: product.id,
        product_name: product.name,
        product_sku: product.sku || product.external_id || "",
        product_color: colorName,
        product_size: sizeName,
        product_image: imgUrl,
        quantity: quantity ?? (product.min_quantity || 1),
        unit_price: product.base_price,
        margin_percent: effectiveMargin,
        sell_price: sellPrice,
        printing_method: "",
        printing_cost: 0,
        printing_setup: 0,
        customization_notes: "",
        colors: product.colors || [],
        size_prices,
      };

      set((state) => ({
        draftItems: [...state.draftItems, draft],
        isQuotePanelOpen: true,
      }));
    } catch (err) {
      console.error("addToQuote error:", err);
    }
  },

  updateDraftItem: (localId, updates) =>
    set((state) => ({
      draftItems: state.draftItems.map((d) =>
        d.localId === localId ? { ...d, ...updates } : d
      ),
    })),

  setDraftNumber: (value) => set({ draftNumber: value }),
  setDraftClientName: (value) => set({ draftClientName: value }),
  setDraftClientCompany: (value) => set({ draftClientCompany: value }),
  setDraftClientEmail: (value) => set({ draftClientEmail: value }),
  setDraftCompanyId: (value) => set({ draftCompanyId: value }),
  setDraftClient: (field, value) => {
    if (field === "Number") set({ draftNumber: value });
    else if (field === "Name") set({ draftClientName: value });
    else if (field === "Company") set({ draftClientCompany: value });
    else if (field === "Email") set({ draftClientEmail: value });
    else if (field === "CompanyId") set({ draftCompanyId: value });
  },

  loadQuoteAsDraft: (quote) => {
    const drafts: DraftItem[] = (quote.items || []).map((it: QuoteItem, idx: number) => ({
      localId: `draft-edit-${quote.id}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
      product_id: it.product_id,
      product_name: it.product_name || "",
      product_sku: it.product_sku || "",
      product_color: it.product_color || "",
      product_size: it.product_size || "",
      product_image: it.product_image || "",
      quantity: it.quantity || 1,
      unit_price: it.unit_price || 0,
      margin_percent: it.margin_percent || 0,
      sell_price: it.sell_price || 0,
      printing_method: it.printing_method || "",
      printing_cost: it.printing_cost || 0,
      printing_setup: it.printing_setup || 0,
      customization_notes: it.customization_notes || "",
      colors: [],
    }));
    set({
      draftItems: drafts,
      draftNumber: quote.number || "",
      draftClientName: quote.client_name || "",
      draftClientCompany: quote.client_company || "",
      draftClientEmail: quote.client_email || "",
      draftCompanyId: quote.company_id || "",
      editingQuoteId: quote.id,
      isQuotePanelOpen: true,
      currentQuote: null,
    });
  },

  duplicateQuoteAsDraft: (quote) => {
    const drafts: DraftItem[] = (quote.items || []).map((it: QuoteItem, idx: number) => ({
      localId: `draft-dup-${quote.id}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
      product_id: it.product_id,
      product_name: it.product_name || "",
      product_sku: it.product_sku || "",
      product_color: it.product_color || "",
      product_size: it.product_size || "",
      product_image: it.product_image || "",
      quantity: it.quantity || 1,
      unit_price: it.unit_price || 0,
      margin_percent: it.margin_percent || 0,
      sell_price: it.sell_price || 0,
      printing_method: it.printing_method || "",
      printing_cost: it.printing_cost || 0,
      printing_setup: it.printing_setup || 0,
      customization_notes: it.customization_notes || "",
      colors: [],
    }));
    set({
      draftItems: drafts,
      draftNumber: "",
      draftClientName: quote.client_name || "",
      draftClientCompany: quote.client_company || "",
      draftClientEmail: quote.client_email || "",
      draftCompanyId: quote.company_id || "",
      editingQuoteId: null,
      isQuotePanelOpen: true,
      currentQuote: null,
    });
  },

  appendQuoteAsDraft: (quote) => {
    const newDrafts: DraftItem[] = (quote.items || []).map((it: QuoteItem, idx: number) => ({
      localId: `draft-ai-${quote.id}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
      product_id: it.product_id,
      product_name: it.product_name || "",
      product_sku: it.product_sku || "",
      product_color: it.product_color || "",
      product_size: it.product_size || "",
      product_image: it.product_image || "",
      quantity: it.quantity || 1,
      unit_price: it.unit_price || 0,
      margin_percent: it.margin_percent || 0,
      sell_price: it.sell_price || 0,
      printing_method: it.printing_method || "",
      printing_cost: it.printing_cost || 0,
      printing_setup: it.printing_setup || 0,
      customization_notes: it.customization_notes || "",
      colors: [],
    }));
    set((state) => {
      // Dedupe by product_id — if the same product already exists, skip
      const existingIds = new Set(
        state.draftItems.map((d) => d.product_id).filter(Boolean)
      );
      const toAdd = newDrafts.filter(
        (d) => !d.product_id || !existingIds.has(d.product_id)
      );
      return {
        draftItems: [...state.draftItems, ...toAdd],
        isQuotePanelOpen: true,
        // Pre-fill client fields if empty
        draftClientName: state.draftClientName || quote.client_name || "",
        draftClientCompany: state.draftClientCompany || quote.client_company || "",
        draftClientEmail: state.draftClientEmail || quote.client_email || "",
      };
    });
  },

  clearDraft: () =>
    set({
      draftItems: [],
      draftNumber: "",
      draftClientName: "",
      draftClientCompany: "",
      draftClientEmail: "",
      draftCompanyId: "",
      editingQuoteId: null,
      currentQuote: null,
    }),

  removeFromQuote: (itemIndex) =>
    set((state) => {
      // Remove from draft items
      if (state.draftItems.length > 0) {
        const newDraft = [...state.draftItems];
        newDraft.splice(itemIndex, 1);
        return { draftItems: newDraft };
      }
      if (!state.currentQuote) return state;
      const items = state.currentQuote.items.filter((_, i) => i !== itemIndex);
      const total = items.reduce((sum, item) => sum + item.total, 0);
      return {
        currentQuote: { ...state.currentQuote, items, total },
      };
    }),

  addToPackman: (product) =>
    set((state) => {
      if (state.packmanProducts.some((p) => p.id === product.id)) return state;
      const bkProduct: BrandKitProduct = {
        id: product.id,
        sku: product.sku || product.external_id || product.supplier_code || "",
        name: product.name,
        supplier: product.category || "",
        category: product.category || "",
        color: product.color_names?.[0] || product.colors?.[0]?.name || "",
        color_hex: product.colors?.[0]?.hex || "",
        stock: product.stock || product.total_stock || 0,
        image_url: product.image_url || product.images?.[0] || "",
        images: product.images || [product.image_url || ""].filter(Boolean),
        min_order: product.min_quantity || 1,
        print_areas: [],
      };
      return { packmanProducts: [...state.packmanProducts, bkProduct] };
    }),

  removeFromPackman: (id) =>
    set((state) => ({
      packmanProducts: state.packmanProducts.filter((p) => p.id !== id),
    })),

  clearPackman: () => set({ packmanProducts: [] }),
}), {
  name: "promoquote-store",
  storage: createJSONStorage(() => localStorage),
  partialize: (state) => ({
    draftItems: state.draftItems,
    draftNumber: state.draftNumber,
    draftClientName: state.draftClientName,
    draftClientCompany: state.draftClientCompany,
    draftClientEmail: state.draftClientEmail,
    draftCompanyId: state.draftCompanyId,
    editingQuoteId: state.editingQuoteId,
    isQuotePanelOpen: state.isQuotePanelOpen,
    packmanProducts: state.packmanProducts,
  }),
}));
