"use client";

import { useState, useEffect, useMemo } from "react";
import {
  X,
  Package,
  ShoppingCart,
  Palette,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { getProductVariants } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Product, ProductVariant, VariantsResponse } from "@/types";

interface ProductDetailModalProps {
  product: Product | null;
  open: boolean;
  onClose: () => void;
  onAddToQuote?: (product: Product) => void;
}

/** Group variants by color name, collecting sizes within each group. */
interface ColorGroup {
  colorName: string;
  hex: string;
  image: string;
  sizes: { size: string; variant: ProductVariant; variantIdx: number }[];
  totalStock: number;
}

const SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "XXL", "3XL", "XXXL", "4XL", "5XL"];

// Human-readable Romanian labels for common spec keys across suppliers.
// Keys are matched case/diacritic-insensitive after normalization.
const SPEC_LABELS: Record<string, string> = {
  size: "Dimensiuni",
  dimensions: "Dimensiuni",
  dimension: "Dimensiuni",
  textile_size: "Mărime textilă",
  weight: "Greutate",
  material: "Material",
  material_1: "Material",
  material_2: "Material secundar",
  material_3: "Material terțiar",
  material_1_weight: "Densitate material",
  material_2_weight: "Densitate material secundar",
  capacity: "Capacitate",
  volume: "Volum",
  country_of_origin: "Țara de origine",
  origin: "Țara de origine",
  gender: "Gen",
  brand: "Brand",
  pack_size: "Mărime pachet",
  carton_size: "Mărime carton",
  package: "Ambalare",
  packaging: "Ambalare",
  color: "Culoare",
  diameter: "Diametru",
  height: "Înălțime",
  width: "Lățime",
  length: "Lungime",
  battery: "Baterie",
  power: "Putere",
};

function normalizeSpecKey(k: string): string {
  return k.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
}

function labelForSpec(key: string): string {
  const norm = normalizeSpecKey(key);
  if (SPEC_LABELS[norm]) return SPEC_LABELS[norm];
  // Fallback: capitalize first letter, replace _ with space
  return key
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
}

function formatSpecValue(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return "";
  }
}

function sizeSort(a: string, b: string): number {
  const ai = SIZE_ORDER.indexOf(a.toUpperCase());
  const bi = SIZE_ORDER.indexOf(b.toUpperCase());
  if (ai >= 0 && bi >= 0) return ai - bi;
  if (ai >= 0) return -1;
  if (bi >= 0) return 1;
  return a.localeCompare(b);
}

export default function ProductDetailModal({
  product,
  open,
  onClose,
  onAddToQuote,
}: ProductDetailModalProps) {
  const addToPackman = useStore((s) => s.addToPackman);
  const draftItems = useStore((s) => s.draftItems);
  const currentQuote = useStore((s) => s.currentQuote);
  const [data, setData] = useState<VariantsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [imgIdx, setImgIdx] = useState(0);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (!open || !product?.supplier_code) {
      setData(null);
      setSelectedIdx(0);
      setImgIdx(0);
      return;
    }

    let cancelled = false;
    setLoading(true);

    getProductVariants(product.supplier_code, product.integration_id)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          const idx = res.variants.findIndex((v) => v.id === product.id);
          setSelectedIdx(idx >= 0 ? idx : 0);
          setImgIdx(0);
          setImgError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, product?.supplier_code, product?.integration_id, product?.id]);

  // Group variants by color
  const colorGroups = useMemo<ColorGroup[]>(() => {
    if (!data) return [];
    const map = new Map<string, ColorGroup>();
    data.variants.forEach((v, idx) => {
      const colorName = v.color?.name?.trim() || "N/A";
      const size = v.specifications?.size || "";
      if (!map.has(colorName)) {
        map.set(colorName, {
          colorName,
          hex: v.color?.hex || "",
          image: v.color?.image || "",
          sizes: [],
          totalStock: 0,
        });
      }
      const g = map.get(colorName)!;
      g.sizes.push({ size, variant: v, variantIdx: idx });
      g.totalStock += v.stock;
    });
    // Sort sizes within each group
    const groups = Array.from(map.values());
    groups.forEach((g) => {
      g.sizes.sort((a: ColorGroup["sizes"][0], b: ColorGroup["sizes"][0]) =>
        sizeSort(a.size, b.size)
      );
    });
    return groups;
  }, [data]);

  // Determine if product has sizes
  const hasSizes = useMemo(
    () => colorGroups.some((g) => g.sizes.some((s) => s.size)),
    [colorGroups]
  );

  // Which color group is selected
  const selectedColorGroup = useMemo(() => {
    return colorGroups.find((g) =>
      g.sizes.some((s) => s.variantIdx === selectedIdx)
    );
  }, [colorGroups, selectedIdx]);

  // Check if product is already in draft or saved quote
  const isAlreadyInQuote = (() => {
    const code = product?.supplier_code || product?.external_id || "";
    if (!code) return false;
    // Check draft items
    for (const d of draftItems) {
      if (d.product_sku === code || d.product_id === product?.id) return true;
    }
    // Check saved quote items
    if (currentQuote?.items) {
      for (const it of currentQuote.items) {
        if (it.product_sku === code || it.product_id === product?.id) return true;
      }
    }
    return false;
  })();

  if (!open || !product) return null;

  const variant: ProductVariant | undefined = data?.variants[selectedIdx];
  const images = variant?.images?.length
    ? variant.images
    : [variant?.primary_image || ""];
  const currentImage = images[imgIdx] || "";

  const handleSelectColor = (group: ColorGroup) => {
    // Select the first size in this color group
    if (group.sizes.length > 0) {
      const newIdx = group.sizes[0].variantIdx;
      console.log("[COLOR]", group.colorName, "variantIdx=", newIdx, "primary=", data?.variants[newIdx]?.primary_image?.slice(-30));
      setSelectedIdx(newIdx);
      setImgIdx(0);
      setImgError(false);
    }
  };

  const handleSelectSize = (variantIdx: number) => {
    setSelectedIdx(variantIdx);
    setImgIdx(0);
    setImgError(false);
  };

  const handleAddToQuote = () => {
    if (!variant || !onAddToQuote) return;
    // Use the selected color, not the full colors array
    const selectedColor = variant.color?.name || selectedColorGroup?.colorName || "";
    // Use whichever image the user is currently viewing in the gallery
    const selectedImage = currentImage || variant.primary_image;
    const p: Product = {
      id: variant.id,
      external_id: variant.external_id,
      supplier_code: variant.supplier_code,
      name: variant.name,
      description: variant.description,
      category: variant.category,
      sku: variant.external_id,
      base_price: variant.base_price,
      sell_price: variant.sell_price,
      sell_price_ron: variant.sell_price_ron,
      currency: variant.currency,
      min_quantity: variant.min_order_qty,
      image_url: selectedImage,
      images: variant.images,
      color_names: [selectedColor],
      colors: variant.colors,
      material: variant.specifications?.material || "",
      size: variant.specifications?.size || "",
      print_area: "",
      stock: variant.stock,
      brand: variant.brand,
    };
    onAddToQuote(p);
    onClose();
  };

  const handlePackIt = () => {
    if (!variant) return;
    const selectedImage = currentImage || variant.primary_image;
    const p: Product = {
      id: variant.id,
      external_id: variant.external_id,
      supplier_code: variant.supplier_code,
      name: variant.name,
      description: variant.description,
      category: variant.category,
      sku: variant.external_id,
      base_price: variant.base_price,
      sell_price: variant.sell_price,
      sell_price_ron: variant.sell_price_ron,
      currency: variant.currency,
      min_quantity: variant.min_order_qty,
      image_url: selectedImage,
      images: variant.images,
      color_names: [variant.color?.name || selectedColorGroup?.colorName || ""],
      colors: variant.colors,
      material: variant.specifications?.material || "",
      size: variant.specifications?.size || "",
      print_area: "",
      stock: variant.stock,
      brand: variant.brand,
    };
    addToPackman(p);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-2 rounded-full bg-white/80 hover:bg-gray-100 transition-colors"
        >
          <X className="w-5 h-5 text-gray-600" />
        </button>

        {loading ? (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
            <span className="ml-3 text-gray-500">Se incarca variantele...</span>
          </div>
        ) : !data || !variant ? (
          <div className="flex flex-col items-center justify-center py-32 text-gray-400">
            <Package className="w-12 h-12 mb-3" />
            <p>Nu s-au gasit variante</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
            {/* Left - Image gallery */}
            <div className="relative bg-gray-50 p-6 flex items-center justify-center min-h-[400px]">
              {currentImage && !imgError ? (
                <img
                  key={`${selectedIdx}-${imgIdx}`}
                  src={currentImage}
                  alt={variant.name}
                  className="max-w-full max-h-[400px] object-contain"
                  onError={() => setImgError(true)}
                />
              ) : (
                <Package className="w-20 h-20 text-gray-300" />
              )}

              {/* Image navigation */}
              {images.length > 1 && (
                <>
                  <button
                    onClick={() =>
                      setImgIdx((prev) =>
                        prev > 0 ? prev - 1 : images.length - 1
                      )
                    }
                    className="absolute left-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-white/80 shadow hover:bg-white transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() =>
                      setImgIdx((prev) =>
                        prev < images.length - 1 ? prev + 1 : 0
                      )
                    }
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-white/80 shadow hover:bg-white transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                  <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5">
                    {images.map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setImgIdx(i)}
                        className={`w-2 h-2 rounded-full transition-colors ${
                          i === imgIdx ? "bg-blue-500" : "bg-gray-300"
                        }`}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Right - Product info */}
            <div className="p-6 flex flex-col">
              <p className="text-xs text-gray-400 uppercase tracking-wide">
                {variant.category}
              </p>
              <h2 className="text-xl font-bold text-gray-900 mt-1">
                {variant.name}
              </h2>
              {variant.brand && (
                <p className="text-sm text-gray-500 mt-0.5">{variant.brand}</p>
              )}

              {/* Price */}
              <div className="mt-4">
                <span className="text-2xl font-bold text-blue-600">
                  {variant.sell_price.toFixed(2)} {variant.currency}
                </span>
                {variant.sell_price_ron > 0 && (
                  <span className="text-sm text-gray-400 ml-2">
                    ({variant.sell_price_ron.toFixed(2)} RON)
                  </span>
                )}
                {variant.min_order_qty > 1 && (
                  <span className="text-xs text-gray-400 ml-3">
                    min. {variant.min_order_qty} buc.
                  </span>
                )}
              </div>

              {/* Color selector */}
              <div className="mt-5">
                <p className="text-sm font-medium text-gray-700 mb-2">
                  Culori ({colorGroups.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {colorGroups.map((group) => {
                    const isActive = selectedColorGroup?.colorName === group.colorName;
                    return (
                      <button
                        key={group.colorName}
                        onClick={() => handleSelectColor(group)}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border-2 transition-all text-sm ${
                          isActive
                            ? "border-blue-500 bg-blue-50"
                            : "border-gray-200 hover:border-gray-300 bg-white"
                        }`}
                        title={`${group.colorName} - Stoc: ${group.totalStock}`}
                      >
                        {group.image ? (
                          <img
                            src={group.image}
                            alt={group.colorName}
                            className="w-5 h-5 rounded-full border border-gray-200 flex-shrink-0 object-cover"
                          />
                        ) : group.hex ? (
                          <span
                            className="w-5 h-5 rounded-full border border-gray-200 flex-shrink-0"
                            style={{ backgroundColor: group.hex }}
                          />
                        ) : (
                          <span className="w-5 h-5 rounded-full border border-gray-200 bg-gradient-to-br from-gray-100 to-gray-300 flex-shrink-0" />
                        )}
                        <span className="text-gray-700">{group.colorName}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Size selector (only if product has sizes) */}
              {hasSizes && selectedColorGroup && (() => {
                const prices = selectedColorGroup.sizes.map((s) => s.variant.sell_price);
                const hasDiffPrices = prices.length > 1 && new Set(prices.map((p) => p.toFixed(2))).size > 1;
                return (
                <div className="mt-4">
                  <p className="text-sm font-medium text-gray-700 mb-2">
                    Marimi - {selectedColorGroup.colorName}
                    {hasDiffPrices && (
                      <span className="text-xs text-orange-500 font-normal ml-2">
                        (preturi diferite pe marimi)
                      </span>
                    )}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {selectedColorGroup.sizes.map((s) => {
                      const isActive = s.variantIdx === selectedIdx;
                      const outOfStock = s.variant.stock === 0;
                      return (
                        <button
                          key={s.variantIdx}
                          onClick={() => handleSelectSize(s.variantIdx)}
                          className={`px-3 py-1.5 rounded-lg border-2 text-sm font-medium transition-all ${
                            isActive
                              ? "border-blue-500 bg-blue-50 text-blue-700"
                              : outOfStock
                              ? "border-gray-100 bg-gray-50 text-gray-300 line-through"
                              : "border-gray-200 hover:border-gray-300 text-gray-700"
                          }`}
                          title={`${s.size || "Unica"} - ${s.variant.sell_price.toFixed(2)} ${s.variant.currency} - Stoc: ${s.variant.stock}`}
                        >
                          <span>{s.size || "Unica"}</span>
                          {hasDiffPrices && (
                            <span className={`block text-[10px] font-normal ${
                              isActive ? "text-blue-500" : outOfStock ? "text-gray-300" : "text-blue-400"
                            }`}>
                              {s.variant.sell_price.toFixed(2)} €
                            </span>
                          )}
                          <span className={`text-xs font-normal ${
                            outOfStock ? "text-gray-300" : "text-gray-400"
                          }`}>
                            ({s.variant.stock})
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
                );
              })()}

              {/* Selected variant info — base fields */}
              <div className="mt-4 p-3 bg-gray-50 rounded-lg space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Culoare:</span>
                  <span className="font-medium text-gray-900">
                    {variant.color.name || "N/A"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Stoc varianta:</span>
                  <span
                    className={`font-medium ${
                      variant.stock > 0 ? "text-green-600" : "text-red-500"
                    }`}
                  >
                    {variant.stock > 0 ? `${variant.stock} buc.` : "Indisponibil"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Stoc total:</span>
                  <span className="font-medium text-gray-900">
                    {data.total_stock} buc.
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Cod:</span>
                  <span className="font-mono text-gray-700 text-xs">
                    {variant.external_id}
                  </span>
                </div>
                {variant.min_order_qty > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Comandă minimă:</span>
                    <span className="font-medium text-gray-900">
                      {variant.min_order_qty} buc.
                    </span>
                  </div>
                )}

                {/* All supplier-provided specifications */}
                {variant.specifications &&
                  Object.entries(variant.specifications)
                    .filter(([, v]) => {
                      const s = formatSpecValue(v);
                      return s && s.trim().length > 0;
                    })
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between text-sm gap-3">
                        <span className="text-gray-500 flex-shrink-0">
                          {labelForSpec(k)}:
                        </span>
                        <span className="font-medium text-gray-900 text-right break-words">
                          {formatSpecValue(v)}
                        </span>
                      </div>
                    ))}
              </div>

              {/* Description — full text */}
              {(variant.description || variant.short_description) && (
                <div className="mt-4">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                    Descriere
                  </h4>
                  <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed">
                    {variant.description || variant.short_description}
                  </p>
                </div>
              )}

              {/* Printing options */}
              {Array.isArray(variant.printing_options) &&
                variant.printing_options.length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                      Opțiuni personalizare
                    </h4>
                    <div className="space-y-1.5">
                      {variant.printing_options.map((opt, idx) => {
                        const o = opt as Record<string, unknown>;
                        const position =
                          (typeof o.position === "string" && o.position) ||
                          (typeof o.zone === "string" && o.zone) ||
                          "";
                        const techniques = Array.isArray(o.techniques)
                          ? (o.techniques as Record<string, unknown>[])
                          : [];
                        const techNames = techniques
                          .map((t) => (typeof t.name === "string" ? t.name : ""))
                          .filter(Boolean)
                          .join(", ");
                        const firstTech = techniques[0] || {};
                        const dims =
                          firstTech.max_width_mm && firstTech.max_height_mm
                            ? `${firstTech.max_width_mm} × ${firstTech.max_height_mm} mm`
                            : "";
                        return (
                          <div
                            key={idx}
                            className="text-xs text-gray-700 bg-gray-50 rounded-md px-2.5 py-1.5"
                          >
                            {position && (
                              <span className="font-medium">{position}</span>
                            )}
                            {techNames && (
                              <span>
                                {position ? " · " : ""}
                                {techNames}
                              </span>
                            )}
                            {dims && (
                              <span className="text-gray-500">
                                {(position || techNames) ? " · " : ""}max {dims}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

              {/* Action buttons */}
              <div className="mt-auto pt-4 flex gap-2">
                {onAddToQuote && (
                  <button
                    onClick={handleAddToQuote}
                    disabled={variant.stock === 0 || isAlreadyInQuote}
                    className={`flex-1 flex items-center justify-center gap-2 py-3 font-medium rounded-xl transition-colors disabled:cursor-not-allowed ${
                      isAlreadyInQuote
                        ? "bg-green-100 text-green-700 border border-green-300"
                        : "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300"
                    }`}
                  >
                    <ShoppingCart className="w-4 h-4" />
                    {isAlreadyInQuote ? "Adaugat in oferta" : "Adauga la oferta"}
                  </button>
                )}
                <button
                  onClick={handlePackIt}
                  disabled={variant.stock === 0}
                  className="flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 text-white font-medium rounded-xl hover:bg-purple-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                  title="Trimite la Packman AI"
                >
                  <Palette className="w-4 h-4" />
                  Pack it
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
