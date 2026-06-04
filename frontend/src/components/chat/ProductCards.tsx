"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  X,
  Package,
  Palette,
  Ruler,
  Layers,
  ShoppingCart,
  Printer,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import type { Product } from "@/types";

interface ProductCardsProps {
  products: Product[];
}

export default function ProductCards({ products }: ProductCardsProps) {
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
        {products.map((product, index) => (
          <ProductCard
            key={product.id}
            product={product}
            index={index}
            onSelect={() => setSelectedProduct(product)}
          />
        ))}
      </div>

      <AnimatePresence>
        {selectedProduct && (
          <ProductModal
            product={selectedProduct}
            onClose={() => setSelectedProduct(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function ProductCard({
  product,
  index,
  onSelect,
}: {
  product: Product;
  index: number;
  onSelect: () => void;
}) {
  const { addToQuote, draftItems, currentQuote } = useStore();
  const [isAdding, setIsAdding] = useState(false);

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

  const handleAdd = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isInQuote) return;
    setIsAdding(true);
    try {
      await addToQuote(product);
    } catch {
      // handled by store
    }
    setIsAdding(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      onClick={onSelect}
      className="glass-card p-3 cursor-pointer group/card"
    >
      {/* Image */}
      <div className="relative w-full aspect-square rounded-xl overflow-hidden mb-3 bg-dark-800">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            className="w-full h-full object-contain p-2 group-hover/card:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Package size={32} className="text-dark-200" />
          </div>
        )}

        {/* Customizable badge */}
        {(product.customizable || product.print_area) && (
          <div className="absolute top-2 left-2 flex items-center gap-1 bg-accent/90 backdrop-blur-sm text-white text-[10px] font-semibold px-2 py-1 rounded-lg">
            <Printer size={10} />
            Personalizabil
          </div>
        )}

        {/* Stock indicator */}
        <div
          className={cn(
            "absolute top-2 right-2 text-[10px] font-medium px-2 py-1 rounded-lg backdrop-blur-sm",
            product.stock > 10
              ? "bg-success/20 text-green-400"
              : product.stock > 0
              ? "bg-yellow-500/20 text-yellow-400"
              : "bg-red-500/20 text-red-400"
          )}
        >
          {product.stock > 10
            ? "In stoc"
            : product.stock > 0
            ? `${product.stock} buc`
            : "Stoc epuizat"}
        </div>
      </div>

      {/* Info */}
      <div className="space-y-2">
        <h4 className="font-medium text-sm text-dark-50 line-clamp-2 leading-tight">
          {product.name}
        </h4>
        <div className="flex items-center gap-2">
          <p className="text-[11px] text-dark-200 font-mono">{product.sku}</p>
          {product.supplier_code && (
            <p className="text-[11px] text-dark-300 font-mono">
              Cod: {product.supplier_code}
            </p>
          )}
        </div>

        <div className="flex items-end justify-between pt-1">
          <div>
            <p className="text-xl font-bold text-dark-50">
              {(product.sell_price ?? product.base_price).toFixed(2)}
              <span className="text-xs font-normal text-dark-200 ml-1">
                EUR
              </span>
            </p>
            {product.sell_price_ron && (
              <p className="text-sm text-dark-100">
                {product.sell_price_ron.toFixed(2)}
                <span className="text-xs font-normal text-dark-200 ml-1">
                  RON
                </span>
              </p>
            )}
            {product.min_quantity > 1 && (
              <p className="text-[10px] text-dark-200">
                min. {product.min_quantity} buc
              </p>
            )}
          </div>

          <button
            onClick={handleAdd}
            disabled={isAdding || product.stock === 0 || isInQuote}
            className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl transition-all",
              isInQuote
                ? "bg-green-500/10 text-green-400 cursor-not-allowed"
                : "bg-accent/10 text-accent-hover hover:bg-accent/20 active:scale-95",
              "disabled:opacity-70 disabled:cursor-not-allowed"
            )}
          >
            <Plus size={14} />
            {isInQuote ? "In ofertă" : isAdding ? "..." : "Adaugă"}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function ProductModal({
  product,
  onClose,
}: {
  product: Product;
  onClose: () => void;
}) {
  const { addToQuote } = useStore();
  const [quantity, setQuantity] = useState(product.min_quantity || 1);
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = async () => {
    setIsAdding(true);
    try {
      await addToQuote(product, quantity);
      onClose();
    } catch {
      // handled
    }
    setIsAdding(false);
  };

  const details = [
    { icon: Palette, label: "Culoare", value: product.color_names?.join(", ") },
    { icon: Layers, label: "Material", value: product.material },
    { icon: Ruler, label: "Dimensiune", value: product.size },
    { icon: Printer, label: "Zonă print", value: product.print_area },
  ].filter((d) => d.value);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-lg glass-panel rounded-3xl overflow-hidden shadow-2xl shadow-black/40"
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 rounded-xl bg-dark-400/80 backdrop-blur flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-300 transition-all"
        >
          <X size={16} />
        </button>

        {/* Image */}
        <div className="relative h-56 bg-dark-800 flex items-center justify-center">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt={product.name}
              className="max-h-full max-w-full object-contain p-6"
            />
          ) : (
            <Package size={48} className="text-dark-300" />
          )}

          {(product.customizable || product.print_area) && (
            <div className="absolute bottom-3 left-3 flex items-center gap-1.5 bg-accent/90 backdrop-blur text-white text-xs font-semibold px-3 py-1.5 rounded-xl">
              <Printer size={12} />
              Personalizabil
            </div>
          )}
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <p className="text-[11px] font-mono text-dark-200">
                {product.sku}
              </p>
              {product.supplier_code && (
                <p className="text-[11px] font-mono text-dark-300">
                  Cod: {product.supplier_code}
                </p>
              )}
            </div>
            <h3 className="text-lg font-semibold text-dark-50">
              {product.name}
            </h3>
            {product.category && (
              <p className="text-xs text-dark-200 mt-1">{product.category}</p>
            )}
          </div>

          {product.description && (
            <p className="text-sm text-dark-100 leading-relaxed">
              {product.description}
            </p>
          )}

          {/* Details grid */}
          {details.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {details.map((detail) => (
                <div
                  key={detail.label}
                  className="flex items-center gap-2 p-2.5 rounded-xl bg-dark-400/30"
                >
                  <detail.icon size={14} className="text-dark-200" />
                  <div>
                    <p className="text-[10px] text-dark-200 uppercase tracking-wider">
                      {detail.label}
                    </p>
                    <p className="text-xs text-dark-50 font-medium">
                      {detail.value}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Price + Add */}
          <div className="flex items-end justify-between pt-2 border-t border-[rgba(255,255,255,0.06)]">
            <div>
              <p className="text-2xl font-bold text-dark-50">
                {(product.sell_price ?? product.base_price).toFixed(2)}
                <span className="text-sm font-normal text-dark-200 ml-1">
                  EUR / buc
                </span>
              </p>
              {product.sell_price_ron && (
                <p className="text-base font-semibold text-dark-100">
                  {product.sell_price_ron.toFixed(2)}
                  <span className="text-xs font-normal text-dark-200 ml-1">
                    RON / buc
                  </span>
                </p>
              )}
              <p
                className={cn(
                  "text-xs mt-0.5",
                  product.stock > 10
                    ? "text-green-400"
                    : product.stock > 0
                    ? "text-yellow-400"
                    : "text-red-400"
                )}
              >
                {product.stock > 10
                  ? `${product.stock} in stoc`
                  : product.stock > 0
                  ? `Doar ${product.stock} disponibile`
                  : "Stoc epuizat"}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center bg-dark-400/40 rounded-xl overflow-hidden">
                <button
                  onClick={() =>
                    setQuantity(Math.max(product.min_quantity || 1, quantity - 1))
                  }
                  className="px-3 py-2 text-dark-100 hover:text-white hover:bg-dark-300 transition-colors"
                >
                  -
                </button>
                <span className="px-3 py-2 text-sm font-medium text-dark-50 min-w-[40px] text-center">
                  {quantity}
                </span>
                <button
                  onClick={() => setQuantity(quantity + 1)}
                  className="px-3 py-2 text-dark-100 hover:text-white hover:bg-dark-300 transition-colors"
                >
                  +
                </button>
              </div>

              <button
                onClick={handleAdd}
                disabled={isAdding || product.stock === 0}
                className={cn(
                  "flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm transition-all",
                  "bg-accent text-white hover:bg-accent-hover active:scale-95 glow-accent",
                  "disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
                )}
              >
                <ShoppingCart size={16} />
                {isAdding ? "Se adaugă..." : "Adaugă"}
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
