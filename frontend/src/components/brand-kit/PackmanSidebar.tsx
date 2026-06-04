"use client";

import { useState } from "react";
import {
  Upload,
  X,
  Trash2,
  Eye,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { UNIFIED_COLOR_LIST } from "@/lib/brand-kit/color-mapping";
import { uploadLogo, getLogoUrl } from "@/lib/brand-kit/api";
import type { BrandKitProduct } from "@/lib/brand-kit/types";
import type { Company } from "@/types";
import { cn } from "@/lib/cn";

interface PackmanSidebarProps {
  selectedColors: string[];
  onColorsChange: (colors: string[]) => void;
  logoUrl: string | null;
  onLogoChange: (url: string | null, base64: string | null) => void;
  clientName: string;
  onClientNameChange: (name: string) => void;
  selectedProducts: BrandKitProduct[];
  mockups: Record<string, string>;
  onRemoveProduct: (id: string) => void;
  onOpenMockup: (product: BrandKitProduct) => void;
  flash?: boolean;
  companies: Company[];
  selectedCompanyId: string;
  onCompanyChange: (id: string) => void;
}

export default function PackmanSidebar({
  selectedColors,
  onColorsChange,
  logoUrl,
  onLogoChange,
  clientName,
  onClientNameChange,
  selectedProducts,
  mockups,
  onRemoveProduct,
  onOpenMockup,
  flash,
  companies,
  selectedCompanyId,
  onCompanyChange,
}: PackmanSidebarProps) {
  const [uploading, setUploading] = useState(false);
  const [colorsExpanded, setColorsExpanded] = useState(true);
  const [productsExpanded, setProductsExpanded] = useState(true);

  const toggleColor = (colorGroup: string) => {
    if (selectedColors.includes(colorGroup)) {
      onColorsChange(selectedColors.filter((c) => c !== colorGroup));
    } else {
      onColorsChange([...selectedColors, colorGroup]);
    }
  };

  const handleLogoFile = async (file: File) => {
    if (!file.type.includes("png")) {
      alert("Doar fișiere PNG");
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = reader.result as string;
      setUploading(true);
      try {
        const result = await uploadLogo(file);
        onLogoChange(getLogoUrl(result.filename), base64);
      } catch {
        onLogoChange(base64, base64);
      } finally {
        setUploading(false);
      }
    };
    reader.readAsDataURL(file);
  };

  return (
    <aside className="w-[280px] h-full bg-dark-800/50 backdrop-blur-xl border-r border-[--border] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 pb-3 border-b border-[--border]">
        <h2 className="text-sm font-bold text-dark-50">Brand Setup</h2>
        <p className="text-[10px] text-dark-300 mt-0.5">
          Logo și culori brand
        </p>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Company selector */}
        {companies.length > 0 && (
          <div className="p-4 pb-3">
            <label className="text-[10px] text-dark-300 uppercase tracking-wider font-semibold mb-1.5 block">
              Firma ofertantă
            </label>
            <select
              value={selectedCompanyId}
              onChange={(e) => onCompanyChange(e.target.value)}
              className="w-full text-xs bg-dark-600/50 border border-[rgba(255,255,255,0.08)] rounded-lg px-3 py-2 text-dark-50 focus:outline-none focus:border-accent/30"
            >
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.is_default ? " ★" : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Client name */}
        <div className="p-4 pb-3">
          <label className="text-[10px] text-dark-300 uppercase tracking-wider font-semibold mb-1.5 block">
            Client
          </label>
          <input
            type="text"
            value={clientName}
            onChange={(e) => onClientNameChange(e.target.value)}
            placeholder="Nume client..."
            className="w-full text-xs bg-dark-600/50 border border-[rgba(255,255,255,0.08)] rounded-lg px-3 py-2 text-dark-50 placeholder:text-dark-300 focus:outline-none focus:border-accent/30"
          />
        </div>

        {/* Logo upload */}
        <div className="px-4 pb-3">
          <label className="text-[10px] text-dark-300 uppercase tracking-wider font-semibold mb-1.5 block">
            Logo PNG
          </label>
          {logoUrl ? (
            <div className="relative group">
              <img
                src={logoUrl}
                alt="Logo"
                className="h-16 max-w-full object-contain bg-white/10 rounded-lg p-2"
              />
              <button
                onClick={() => onLogoChange(null, null)}
                className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ) : (
            <label className="flex items-center gap-2 px-3 py-2.5 bg-dark-600/50 border border-dashed border-[rgba(255,255,255,0.12)] rounded-lg cursor-pointer hover:border-accent/30 transition-colors">
              {uploading ? (
                <div className="animate-spin w-4 h-4 border-2 border-accent border-t-transparent rounded-full" />
              ) : (
                <Upload className="w-4 h-4 text-dark-300" />
              )}
              <span className="text-xs text-dark-300">
                {uploading ? "Se încarcă..." : "Încarcă logo PNG"}
              </span>
              <input
                type="file"
                accept="image/png"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleLogoFile(f);
                }}
              />
            </label>
          )}
        </div>

        {/* Colors */}
        <div className="px-4 pb-3">
          <button
            onClick={() => setColorsExpanded(!colorsExpanded)}
            className="flex items-center justify-between w-full mb-1.5"
          >
            <span className="text-[10px] text-dark-300 uppercase tracking-wider font-semibold">
              Culori Brand ({selectedColors.length})
            </span>
            {colorsExpanded ? (
              <ChevronUp className="w-3 h-3 text-dark-300" />
            ) : (
              <ChevronDown className="w-3 h-3 text-dark-300" />
            )}
          </button>
          {colorsExpanded && (
            <div className="flex flex-wrap gap-1.5">
              {UNIFIED_COLOR_LIST.map((color) => {
                const sel = selectedColors.includes(color.colorGroup);
                return (
                  <button
                    key={color.key}
                    onClick={() => toggleColor(color.colorGroup)}
                    className={cn(
                      "flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium border transition-all",
                      sel
                        ? "border-accent/40 bg-accent/10 text-accent-hover"
                        : "border-[rgba(255,255,255,0.08)] bg-dark-600/30 text-dark-200 hover:border-[rgba(255,255,255,0.15)]",
                    )}
                    title={color.label}
                  >
                    <span
                      className="w-3 h-3 rounded-full border border-[rgba(255,255,255,0.15)] flex-shrink-0"
                      style={{ backgroundColor: color.hex }}
                    />
                    {color.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected products — always visible */}
        <div className={cn(
          "px-4 pb-3 transition-colors duration-700",
          flash && "bg-green-500/10"
        )}>
          <button
            onClick={() => setProductsExpanded(!productsExpanded)}
            className="flex items-center justify-between w-full mb-1.5"
          >
            <span className={cn(
              "text-[10px] uppercase tracking-wider font-semibold transition-colors",
              selectedProducts.length > 0 ? "text-accent-hover" : "text-dark-300"
            )}>
              Kit Produse ({selectedProducts.length})
            </span>
            {productsExpanded ? (
              <ChevronUp className="w-3 h-3 text-dark-300" />
            ) : (
              <ChevronDown className="w-3 h-3 text-dark-300" />
            )}
          </button>
          {productsExpanded && (
            selectedProducts.length > 0 ? (
              <div className="space-y-1.5">
                {selectedProducts.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center gap-2 p-1.5 bg-dark-600/30 rounded-lg group"
                  >
                    <img
                      src={mockups[p.id] || p.image_url}
                      alt=""
                      className="w-10 h-10 rounded bg-white/10 object-contain p-0.5 flex-shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] text-dark-100 truncate">
                        {p.name}
                      </p>
                      <p className="text-[9px] text-dark-300">{p.sku}</p>
                      {mockups[p.id] && (
                        <span className="text-[8px] text-green-400 font-medium">
                          Mockup salvat
                        </span>
                      )}
                    </div>
                    <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => onOpenMockup(p)}
                        className="p-1 text-dark-300 hover:text-accent rounded"
                        title="Mockup"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onRemoveProduct(p.id)}
                        className="p-1 text-dark-300 hover:text-red-400 rounded"
                        title="Elimină"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-dark-400 italic py-2">
                Niciun produs selectat. Folosește chat-ul sau tab-ul Produse pentru a adăuga.
              </p>
            )
          )}
        </div>
      </div>
    </aside>
  );
}
