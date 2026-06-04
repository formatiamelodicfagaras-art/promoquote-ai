"use client";

import { useState } from "react";
import { ShoppingCart, Palette, Package } from "lucide-react";
import type { Product } from "@/types";
import { useStore } from "@/lib/store";

interface ProductCardProps {
  product: Product;
  onAddToQuote?: (product: Product) => void;
  onClick?: (product: Product) => void;
}

export default function ProductCard({
  product,
  onAddToQuote,
  onClick,
}: ProductCardProps) {
  const addToPackman = useStore((s) => s.addToPackman);
  const draftItems = useStore((s) => s.draftItems);
  const currentQuote = useStore((s) => s.currentQuote);
  const [imgError, setImgError] = useState(false);
  const [hovered, setHovered] = useState(false);

  const isInQuote = (() => {
    const code = product.supplier_code || product.external_id || "";
    if (!code) return false;
    for (const d of draftItems) {
      if (d.product_sku === code || d.product_id === product.id) return true;
    }
    if (currentQuote?.items) {
      for (const it of currentQuote.items) {
        if (it.product_sku === code || it.product_id === product.id) return true;
      }
    }
    return false;
  })();

  // Pick a non-black color image for visual diversity in catalog
  const baseImage = product.image_url || product.images?.[0];
  const rawColorsForImg = product.variant_colors ?? product.colors ?? [];
  const colorsArr = Array.isArray(rawColorsForImg) ? rawColorsForImg : [];
  const blackNames = new Set(["black", "negru", "noir", "schwarz", "nero"]);
  const colorfulVariant = colorsArr.find(
    (c: Record<string, string>) =>
      c?.image &&
      c?.name &&
      !blackNames.has(c.name.toLowerCase()) &&
      !c.image.includes("/color/") &&
      !c.image.includes("swatch")
  );
  const imageUrl = colorfulVariant?.image || baseImage;
  const hasImage = imageUrl && !imgError;
  const totalStock = product.total_stock ?? product.stock;
  const inStock = totalStock > 0;
  const variantCount = product.variant_count ?? 1;
  const rawColors = product.variant_colors ?? product.colors ?? [];
  const colors = Array.isArray(rawColors) ? rawColors : [];

  return (
    <div
      className="group relative bg-white rounded-xl border border-gray-200 overflow-hidden transition-all hover:shadow-lg hover:border-gray-300 cursor-pointer"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onClick?.(product)}
    >
      {/* Image */}
      <div className="relative aspect-square bg-white overflow-hidden ring-1 ring-inset ring-gray-200/60">
        {hasImage ? (
          <img
            src={imageUrl}
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
          {inStock ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
              Stoc: {totalStock > 999 ? `${Math.floor(totalStock / 1000)}k+` : totalStock}
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
              Indisponibil
            </span>
          )}
        </div>

        {/* Variant count badge */}
        {variantCount > 1 && (
          <div className="absolute top-2 right-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
              {variantCount} variante
            </span>
          </div>
        )}

        {/* Hover actions overlay */}
        {hovered && (
          <div className="absolute inset-0 bg-black/5 flex items-end justify-center pb-3 gap-2">
            {onAddToQuote && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isInQuote) onAddToQuote(product);
                }}
                disabled={isInQuote}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg shadow-md transition-colors ${
                  isInQuote
                    ? "bg-green-100 text-green-700 border border-green-300 cursor-not-allowed"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                <ShoppingCart className="w-3.5 h-3.5" />
                {isInQuote ? "In ofertă" : "Adaugă la ofertă"}
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                addToPackman(product);
              }}
              className="flex items-center gap-1.5 px-3 py-2 bg-white text-gray-700 text-xs font-medium rounded-lg shadow-md border border-gray-200 hover:bg-gray-50 transition-colors"
            >
              <Palette className="w-3.5 h-3.5" />
              Pack it
            </button>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-0.5">
          <p className="text-xs text-gray-400">{product.category}</p>
          {product.supplier_code && (
            <span className="text-[11px] text-blue-600 font-mono font-semibold bg-blue-50 px-1.5 py-0.5 rounded">
              {product.supplier_code}
            </span>
          )}
        </div>
        <h3
          className="font-medium text-sm text-gray-900 line-clamp-2 min-h-[2.5rem]"
          dangerouslySetInnerHTML={{
            __html: product._formatted?.name ?? product.name,
          }}
        />

        <div className="flex items-center justify-between mt-2">
          <div>
            <>
              <span className="text-lg font-bold text-blue-600">
                {(product.min_sell_price && product.min_sell_price > 0 ? product.min_sell_price : product.sell_price ?? product.base_price)?.toFixed(2)}{" "}
                €
              </span>
              {product.sell_price_ron && (
                <span className="text-xs text-gray-500 ml-1">
                  ({product.sell_price_ron.toFixed(2)} RON)
                </span>
              )}
            </>
          </div>
          {product.min_quantity > 1 && (
            <span className="text-xs text-gray-400">
              min. {product.min_quantity}
            </span>
          )}
        </div>

        {/* Color swatches */}
        {colors.length > 0 && (
          <div className="flex items-center gap-1 mt-2 flex-wrap">
            {colors.slice(0, 10).map((c, i) => (
              <span
                key={`${c.name}-${i}`}
                className="w-5 h-5 rounded-full border border-gray-200 flex-shrink-0"
                style={{ backgroundColor: c.hex || "#ccc" }}
                title={c.name}
              />
            ))}
            {colors.length > 10 && (
              <span className="text-[10px] text-gray-400 ml-0.5">
                +{colors.length - 10}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
