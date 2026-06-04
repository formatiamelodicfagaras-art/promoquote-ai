"use client";

import { X, FileDown, Trash2, Eye } from "lucide-react";
import type { BrandKitProduct } from "@/lib/brand-kit/types";

interface SelectedProductsPanelProps {
  products: BrandKitProduct[];
  mockups: Record<string, string>;
  onRemove: (id: string) => void;
  onPreviewMockup: (product: BrandKitProduct) => void;
  onGeneratePdf: () => void;
  generatingPdf: boolean;
  clientName: string;
  onClientNameChange: (name: string) => void;
}

export default function SelectedProductsPanel({
  products,
  mockups,
  onRemove,
  onPreviewMockup,
  onGeneratePdf,
  generatingPdf,
  clientName,
  onClientNameChange,
}: SelectedProductsPanelProps) {
  if (products.length === 0) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900">
          Produse selectate ({products.length})
        </h3>
        <button
          onClick={onGeneratePdf}
          disabled={generatingPdf || products.length === 0}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          <FileDown className="w-4 h-4" />
          {generatingPdf ? "Se generează..." : "Generează PDF"}
        </button>
      </div>

      {/* Client name */}
      <div className="mb-3">
        <input
          type="text"
          placeholder="Nume client (pentru PDF)"
          value={clientName}
          onChange={(e) => onClientNameChange(e.target.value)}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
        />
      </div>

      {/* Selected products list */}
      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {products.map((product) => (
          <div
            key={product.id}
            className="flex items-center gap-3 p-2 bg-gray-50 rounded-lg group"
          >
            {/* Thumbnail or mockup */}
            <div className="w-12 h-12 bg-white rounded-lg border border-gray-200 flex-shrink-0 overflow-hidden">
              <img
                src={mockups[product.id] || product.image_url}
                alt={product.name}
                className="w-full h-full object-contain p-0.5"
              />
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                {product.name}
              </p>
              <p className="text-xs text-gray-500">
                {product.sku} — {product.supplier}
              </p>
            </div>

            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => onPreviewMockup(product)}
                className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg"
                title="Mockup"
              >
                <Eye className="w-4 h-4" />
              </button>
              <button
                onClick={() => onRemove(product.id)}
                className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg"
                title="Elimină"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
