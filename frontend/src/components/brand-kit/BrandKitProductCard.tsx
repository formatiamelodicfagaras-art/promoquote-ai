"use client";

import { useState } from "react";
import { Plus, Check, Eye, Package } from "lucide-react";
import type { BrandKitProduct } from "@/lib/brand-kit/types";

interface BrandKitProductCardProps {
  product: BrandKitProduct;
  isSelected: boolean;
  onToggleSelect: (product: BrandKitProduct) => void;
  onPreviewMockup: (product: BrandKitProduct) => void;
  hasLogo: boolean;
}

export default function BrandKitProductCard({
  product,
  isSelected,
  onToggleSelect,
  onPreviewMockup,
  hasLogo,
}: BrandKitProductCardProps) {
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className={`
        relative bg-white rounded-xl border overflow-hidden transition-all group
        ${isSelected ? "border-blue-500 ring-2 ring-blue-100" : "border-gray-200 hover:border-gray-300 hover:shadow-md"}
      `}
    >
      {/* Image */}
      <div className="relative aspect-square bg-gray-50 overflow-hidden">
        {product.image_url && !imgError ? (
          <img
            src={product.image_url}
            alt={product.name}
            loading="lazy"
            className="w-full h-full object-contain p-3 transition-transform group-hover:scale-105"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <Package className="w-12 h-12 text-gray-300" />
          </div>
        )}

        {/* Stock badge */}
        <div className="absolute top-2 left-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
            Stoc: {product.stock > 999 ? `${Math.floor(product.stock / 1000)}k+` : product.stock}
          </span>
        </div>

        {/* Selected check */}
        {isSelected && (
          <div className="absolute top-2 right-2 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
            <Check className="w-4 h-4 text-white" />
          </div>
        )}

        {/* Hover actions */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 flex items-end justify-center pb-3 gap-2 opacity-0 group-hover:opacity-100 transition-all">
          <button
            onClick={(e) => { e.stopPropagation(); onToggleSelect(product); }}
            className={`
              flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg shadow-md transition-colors
              ${isSelected
                ? "bg-red-500 text-white hover:bg-red-600"
                : "bg-blue-600 text-white hover:bg-blue-700"
              }
            `}
          >
            {isSelected ? <Check className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
            {isSelected ? "Selectat" : "Selectează"}
          </button>
          {hasLogo && (
            <button
              onClick={(e) => { e.stopPropagation(); onPreviewMockup(product); }}
              className="flex items-center gap-1.5 px-3 py-2 bg-white text-gray-700 text-xs font-medium rounded-lg shadow-md border border-gray-200 hover:bg-gray-50 transition-colors"
            >
              <Eye className="w-3.5 h-3.5" />
              Mockup
            </button>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="p-3" onClick={() => onToggleSelect(product)}>
        <div className="flex items-center justify-between mb-0.5">
          <p className="text-xs text-gray-400">{product.category || product.supplier}</p>
          <span className="text-[11px] text-blue-600 font-mono font-semibold bg-blue-50 px-1.5 py-0.5 rounded">
            {product.sku}
          </span>
        </div>
        <h3 className="font-medium text-sm text-gray-900 line-clamp-2 min-h-[2.5rem]">
          {product.name}
        </h3>

        {/* Print area info */}
        {product.print_areas.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {product.print_areas.slice(0, 2).map((pa, i) => (
              <span key={i} className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">
                {pa.location} {pa.width_mm > 0 ? `${pa.width_mm}×${pa.height_mm}mm` : ""}
              </span>
            ))}
          </div>
        )}

        {/* Min order */}
        {product.min_order > 1 && (
          <p className="text-xs text-gray-400 mt-1">min. {product.min_order} buc.</p>
        )}
      </div>
    </div>
  );
}
