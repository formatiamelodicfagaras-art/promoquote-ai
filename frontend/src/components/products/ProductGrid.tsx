"use client";

import { useState } from "react";
import type { Product } from "@/types";
import ProductCard from "./ProductCard";
import ProductDetailModal from "./ProductDetailModal";
import { Package } from "lucide-react";

interface ProductGridProps {
  products: Product[];
  loading?: boolean;
  onAddToQuote?: (product: Product) => void;
}

export default function ProductGrid({
  products,
  loading,
  onAddToQuote,
}: ProductGridProps) {
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const handleCardClick = (product: Product) => {
    setSelectedProduct(product);
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setSelectedProduct(null);
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-pulse"
          >
            <div className="aspect-square bg-gray-100" />
            <div className="p-3 space-y-2">
              <div className="h-3 bg-gray-100 rounded w-1/3" />
              <div className="h-4 bg-gray-100 rounded w-full" />
              <div className="h-4 bg-gray-100 rounded w-2/3" />
              <div className="h-5 bg-gray-100 rounded w-1/4 mt-2" />
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
        <p className="text-lg font-medium">Niciun produs gasit</p>
        <p className="text-sm mt-1">
          Incearca o alta cautare sau modifica filtrele
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            onAddToQuote={onAddToQuote}
            onClick={handleCardClick}
          />
        ))}
      </div>

      <ProductDetailModal
        product={selectedProduct}
        open={modalOpen}
        onClose={handleCloseModal}
        onAddToQuote={onAddToQuote}
      />
    </>
  );
}
