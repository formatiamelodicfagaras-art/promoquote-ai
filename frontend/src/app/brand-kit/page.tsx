"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { MessageSquare, Grid3X3, Search, Palette as PaletteIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import type { Company } from "@/types";
import { fetchCompanies } from "@/lib/api";
import type { BrandKitProduct } from "@/lib/brand-kit/types";
import { searchBrandKitProducts, type BrandKitSearchResult } from "@/lib/brand-kit/api";
import PackmanChat from "@/components/brand-kit/PackmanChat";
import PackmanSidebar from "@/components/brand-kit/PackmanSidebar";
import BrandKitProductGrid from "@/components/brand-kit/BrandKitProductGrid";
import MockupPreviewModal from "@/components/brand-kit/MockupPreviewModal";

type Tab = "chat" | "products";

export default function BrandKitPage() {
  const [tab, setTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Company selection
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("");

  useEffect(() => {
    fetchCompanies().then((list) => {
      setCompanies(list);
      const def = list.find((c) => c.is_default);
      if (def) setSelectedCompanyId(def.id);
      else if (list.length > 0) setSelectedCompanyId(list[0].id);
    }).catch(() => {});
  }, []);

  const selectedCompany = companies.find((c) => c.id === selectedCompanyId) || null;

  // Brand setup
  const [selectedColors, setSelectedColors] = useState<string[]>([]);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [logoBase64, setLogoBase64] = useState<string | null>(null);
  const [clientName, setClientName] = useState("");

  // Selection — merge store packmanProducts with local
  const packmanFromStore = useStore((s) => s.packmanProducts);
  const removeFromPackmanStore = useStore((s) => s.removeFromPackman);
  const [localProducts, setLocalProducts] = useState<BrandKitProduct[]>([]);

  // Merge: store products + locally added products (dedup)
  const selectedProducts = (() => {
    const ids = new Set<string>();
    const merged: BrandKitProduct[] = [];
    for (const p of packmanFromStore) {
      if (!ids.has(p.id)) { ids.add(p.id); merged.push(p); }
    }
    for (const p of localProducts) {
      if (!ids.has(p.id)) { ids.add(p.id); merged.push(p); }
    }
    return merged;
  })();
  const selectedIds = new Set(selectedProducts.map((p) => p.id));

  // Mockups
  const [mockups, setMockups] = useState<Record<string, string>>({});
  const [mockupProduct, setMockupProduct] = useState<BrandKitProduct | null>(null);
  const [mockupModalOpen, setMockupModalOpen] = useState(false);

  // Toast notification
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>();
  const showToast = (msg: string) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  // Flash sidebar selected section
  const [sidebarFlash, setSidebarFlash] = useState(false);

  // Product browser state
  const [searchResult, setSearchResult] = useState<BrandKitSearchResult | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browsePage, setBrowsePage] = useState(1);

  const toggleProduct = (product: BrandKitProduct) => {
    if (selectedIds.has(product.id)) {
      // Remove from both stores
      removeFromPackmanStore(product.id);
      setLocalProducts((prev) => prev.filter((p) => p.id !== product.id));
    } else {
      setLocalProducts((prev) => [...prev, product]);
    }
  };

  const removeProduct = (id: string) => {
    removeFromPackmanStore(id);
    setLocalProducts((prev) => prev.filter((p) => p.id !== id));
    setMockups((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const openMockup = (product: BrandKitProduct) => {
    setMockupProduct(product);
    setMockupModalOpen(true);
  };

  const saveMockupToKit = (productId: string, base64: string) => {
    setMockups((prev) => ({ ...prev, [productId]: base64 }));
    // Also ensure the product is in selectedProducts
    if (mockupProduct && !selectedIds.has(mockupProduct.id)) {
      setLocalProducts((prev) => [...prev, mockupProduct]);
    }
    // Flash sidebar & show toast
    const name = mockupProduct?.name || "Produsul";
    showToast(`${name.length > 30 ? name.slice(0, 30) + "…" : name} a fost adăugat în kit`);
    setSidebarFlash(true);
    setTimeout(() => setSidebarFlash(false), 2000);
  };

  // Product browser: search when colors change or tab switches
  const doSearch = useCallback(async (colors: string[], page: number) => {
    setBrowseLoading(true);
    try {
      const result = await searchBrandKitProducts({ colors, page, limit: 40 });
      setSearchResult(result);
    } catch (err) {
      console.error("Browse search error:", err);
    } finally {
      setBrowseLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "products") {
      setBrowsePage(1);
      doSearch(selectedColors, 1);
    }
  }, [tab, selectedColors, doSearch]);

  useEffect(() => {
    if (tab === "products") {
      doSearch(selectedColors, browsePage);
    }
  }, [browsePage]);

  const browseProducts = searchResult?.results || [];
  const browseTotal = searchResult?.total || 0;
  const browseTotalPages = searchResult?.total_pages || 1;

  return (
    <div className="flex h-full relative">
      {/* Mobile brand sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed bottom-4 right-4 z-40 w-12 h-12 rounded-2xl bg-accent text-white flex items-center justify-center shadow-lg glow-accent hover:bg-accent-hover transition-all active:scale-90"
        title="Brand Setup"
      >
        <PaletteIcon size={20} />
        {selectedProducts.length > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-success text-white text-[10px] font-bold flex items-center justify-center">
            {selectedProducts.length}
          </span>
        )}
      </button>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Left sidebar: brand setup */}
      <div className={`
        fixed top-0 left-0 z-50 h-full transform transition-transform duration-200 ease-out
        md:static md:z-auto md:translate-x-0
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
      `}>
      <PackmanSidebar
        selectedColors={selectedColors}
        onColorsChange={setSelectedColors}
        logoUrl={logoUrl}
        onLogoChange={(url, b64) => {
          setLogoUrl(url);
          setLogoBase64(b64);
        }}
        clientName={clientName}
        onClientNameChange={setClientName}
        selectedProducts={selectedProducts}
        mockups={mockups}
        onRemoveProduct={removeProduct}
        onOpenMockup={openMockup}
        flash={sidebarFlash}
        companies={companies}
        selectedCompanyId={selectedCompanyId}
        onCompanyChange={setSelectedCompanyId}
      />
      </div>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Tab bar */}
        <div className="flex items-center gap-1 px-4 pt-3 pb-0">
          <button
            onClick={() => setTab("chat")}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors border border-b-0",
              tab === "chat"
                ? "bg-dark-900/80 text-dark-50 border-[rgba(255,255,255,0.06)]"
                : "text-dark-300 hover:text-dark-100 border-transparent hover:bg-dark-700/30",
            )}
          >
            <MessageSquare className="w-4 h-4" />
            Chat AI
          </button>
          <button
            onClick={() => setTab("products")}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors border border-b-0",
              tab === "products"
                ? "bg-dark-900/80 text-dark-50 border-[rgba(255,255,255,0.06)]"
                : "text-dark-300 hover:text-dark-100 border-transparent hover:bg-dark-700/30",
            )}
          >
            <Grid3X3 className="w-4 h-4" />
            Produse
            {selectedColors.length > 0 && (
              <span className="ml-1 text-[10px] bg-accent/20 text-accent-hover px-1.5 py-0.5 rounded-full">
                {selectedColors.join(", ")}
              </span>
            )}
          </button>
        </div>

        {/* Tab content */}
        {tab === "chat" ? (
          <PackmanChat
            brandColors={selectedColors}
            logoUrl={logoUrl}
            logoBase64={logoBase64}
            clientName={clientName}
            companyId={selectedCompanyId}
            selectedProducts={selectedProducts}
            mockups={mockups}
            onToggleProduct={toggleProduct}
            onOpenMockup={openMockup}
            isProductSelected={(id) => selectedIds.has(id)}
          />
        ) : (
          <div className="flex-1 overflow-y-auto p-4">
            {/* Results header */}
            <div className="flex items-center gap-2 text-sm text-dark-200 mb-4">
              <Search className="w-4 h-4" />
              <span>
                <strong className="text-dark-50">{browseTotal.toLocaleString("ro-RO")}</strong> produse
                {selectedColors.length > 0 && (
                  <> in culorile: <strong className="text-accent-hover">{selectedColors.join(", ")}</strong></>
                )}
                {selectedColors.length === 0 && (
                  <span className="text-dark-300 ml-1">(selecteaza culori din sidebar)</span>
                )}
              </span>
            </div>

            {/* Product grid */}
            <BrandKitProductGrid
              products={browseProducts}
              loading={browseLoading}
              selectedIds={selectedIds}
              onToggleSelect={toggleProduct}
              onPreviewMockup={openMockup}
              hasLogo={!!logoUrl}
            />

            {/* Pagination */}
            {browseTotalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-6">
                <button
                  onClick={() => setBrowsePage((p) => Math.max(1, p - 1))}
                  disabled={browsePage <= 1}
                  className="px-3 py-1.5 text-sm border border-[rgba(255,255,255,0.08)] rounded-lg text-dark-200 hover:bg-dark-700/30 disabled:opacity-50"
                >
                  Anterior
                </button>
                <span className="text-sm text-dark-300">
                  Pagina {browsePage} / {browseTotalPages}
                </span>
                <button
                  onClick={() => setBrowsePage((p) => Math.min(browseTotalPages, p + 1))}
                  disabled={browsePage >= browseTotalPages}
                  className="px-3 py-1.5 text-sm border border-[rgba(255,255,255,0.08)] rounded-lg text-dark-200 hover:bg-dark-700/30 disabled:opacity-50"
                >
                  Urmator
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Mockup preview modal */}
      <MockupPreviewModal
        product={mockupProduct}
        logoUrl={logoUrl}
        open={mockupModalOpen}
        onClose={() => setMockupModalOpen(false)}
        onSaveMockup={saveMockupToKit}
      />

      {/* Toast notification */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300">
          <div className="flex items-center gap-2 px-4 py-3 bg-green-600 text-white text-sm font-medium rounded-xl shadow-lg">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            {toast}
          </div>
        </div>
      )}
    </div>
  );
}
