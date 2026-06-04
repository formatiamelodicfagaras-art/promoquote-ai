"use client";

import { Package } from "lucide-react";
import type { BrandKitProduct } from "@/lib/brand-kit/types";
import BrandKitProductCard from "./BrandKitProductCard";

interface BrandKitProductGridProps {
  products: BrandKitProduct[];
  loading: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (product: BrandKitProduct) => void;
  onPreviewMockup: (product: BrandKitProduct) => void;
  hasLogo: boolean;
}

export default function BrandKitProductGrid({
  products,
  loading,
  selectedIds,
  onToggleSelect,
  onPreviewMockup,
  hasLogo,
}: BrandKitProductGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-pulse">
            <div className="aspect-square bg-gray-100" />
            <div className="p-3 space-y-2">
              <div className="h-3 bg-gray-100 rounded w-1/3" />
              <div className="h-4 bg-gray-100 rounded w-full" />
              <div className="h-4 bg-gray-100 rounded w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400">
        <Package className="w-16 h-16 mb-4 text-gray-300" />
        <p className="text-lg font-medium">Niciun produs găsit</p>
        <p className="text-sm mt-1">Selectează culori din brand pentru a căuta produse</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {products.map((product) => (
        <BrandKitProductCard
          key={product.id}
          product={product}
          isSelected={selectedIds.has(product.id)}
          onToggleSelect={onToggleSelect}
          onPreviewMockup={onPreviewMockup}
          hasLogo={hasLogo}
        />
      ))}
    </div>
  );
}
