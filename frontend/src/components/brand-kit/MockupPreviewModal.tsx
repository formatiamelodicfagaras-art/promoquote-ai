"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  X,
  Download,
  Save,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  RotateCw,
} from "lucide-react";
import type { BrandKitProduct, MockupConfig, WarpMode } from "@/lib/brand-kit/types";
import {
  calculateMockupConfig,
  generateMockup,
  detectWarpMode,
} from "@/lib/brand-kit/mockup-engine";
import { saveMockupZone, getMockupZone } from "@/lib/brand-kit/api";

interface MockupPreviewModalProps {
  product: BrandKitProduct | null;
  logoUrl: string | null;
  open: boolean;
  onClose: () => void;
  onSaveMockup?: (productId: string, base64: string) => void;
}

export default function MockupPreviewModal({
  product,
  logoUrl,
  open,
  onClose,
  onSaveMockup,
}: MockupPreviewModalProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [config, setConfig] = useState<MockupConfig | null>(null);
  const [mockupDataUrl, setMockupDataUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  // Image navigation
  const [imageIndex, setImageIndex] = useState(0);
  const allImages = product?.images?.length ? product.images : [product?.image_url || ""];

  // Print area selector
  const [selectedPrintArea, setSelectedPrintArea] = useState(0);

  // Dragging state for logo repositioning
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number; configX: number; configY: number } | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  const currentImageUrl = allImages[imageIndex] || product?.image_url || "";

  const defaultConfig = useCallback(() => {
    if (!product) return null;
    const printArea = product.print_areas[selectedPrintArea] || product.print_areas[0] || null;
    return calculateMockupConfig(printArea, product.category, product.color_hex);
  }, [product, selectedPrintArea]);

  // Load saved override or calculate default — only when product/open changes
  useEffect(() => {
    if (!product || !open) return;

    let cancelled = false;
    (async () => {
      const saved = await getMockupZone(product.sku, product.supplier);
      if (cancelled) return;
      if (saved) {
        setConfig({
          ...saved,
          rotation: saved.rotation ?? 0,
          warp: saved.warp ?? detectWarpMode(product.category),
          warp_intensity: saved.warp_intensity ?? (saved.warp && saved.warp !== "none" ? 50 : detectWarpMode(product.category) !== "none" ? 50 : 0),
        });
      } else {
        // Inline default calculation — don't depend on selectedPrintArea here
        const printArea = product.print_areas[0] || null;
        setConfig(calculateMockupConfig(printArea, product.category, product.color_hex));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [product?.id, open]);

  // Reset image index when product changes
  useEffect(() => {
    setImageIndex(0);
    setSelectedPrintArea(0);
  }, [product?.id]);

  // Generate mockup when config or image changes
  useEffect(() => {
    if (!config || !product || !logoUrl || !canvasRef.current || !open) return;

    let cancelled = false;
    setGenerating(true);
    generateMockup(canvasRef.current, currentImageUrl, logoUrl, config)
      .then((dataUrl) => {
        if (!cancelled) {
          setMockupDataUrl(dataUrl);
          setGenerating(false);
        }
      })
      .catch(() => {
        if (!cancelled) setGenerating(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, product, logoUrl, open, currentImageUrl]);

  const handleSliderChange = (field: keyof MockupConfig, value: number) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleReset = () => {
    setConfig(defaultConfig());
  };

  const handlePrintAreaChange = (index: number) => {
    setSelectedPrintArea(index);
    if (!product) return;
    const printArea = product.print_areas[index] || null;
    const newConfig = calculateMockupConfig(printArea, product.category, product.color_hex);
    setConfig(newConfig);
  };

  const handleSaveZone = async () => {
    if (!config || !product) return;
    setSaving(true);
    try {
      await saveMockupZone(product.sku, {
        ...config,
        product_sku: product.sku,
        supplier: product.supplier,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = () => {
    if (!mockupDataUrl) return;
    const link = document.createElement("a");
    link.download = `mockup-${product?.sku || "product"}.png`;
    link.href = mockupDataUrl;
    link.click();
  };

  const handleAddToKit = async () => {
    if (mockupDataUrl && product && config) {
      // Auto-save position so it persists
      try {
        await saveMockupZone(product.sku, {
          ...config,
          product_sku: product.sku,
          supplier: product.supplier,
        });
      } catch {
        // ignore save errors
      }
      onSaveMockup?.(product.id, mockupDataUrl);
      onClose();
    }
  };

  // Image navigation
  const handlePrevImage = () => {
    setImageIndex((prev) => (prev > 0 ? prev - 1 : allImages.length - 1));
  };
  const handleNextImage = () => {
    setImageIndex((prev) => (prev < allImages.length - 1 ? prev + 1 : 0));
  };

  // Quick rotation buttons
  const rotateBy = (deg: number) => {
    if (!config) return;
    setConfig({ ...config, rotation: ((config.rotation ?? 0) + deg) % 360 });
  };

  // Drag-to-position handler
  const handlePreviewMouseDown = (e: React.MouseEvent) => {
    if (!config || !previewRef.current) return;
    const rect = previewRef.current.getBoundingClientRect();
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      configX: config.x_percent,
      configY: config.y_percent,
    };
    setIsDragging(true);
    e.preventDefault();
  };

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragStartRef.current || !config || !previewRef.current) return;
      const rect = previewRef.current.getBoundingClientRect();
      const dx = ((e.clientX - dragStartRef.current.x) / rect.width) * 100;
      const dy = ((e.clientY - dragStartRef.current.y) / rect.height) * 100;
      setConfig({
        ...config,
        x_percent: Math.max(0, Math.min(80, dragStartRef.current.configX + dx)),
        y_percent: Math.max(0, Math.min(80, dragStartRef.current.configY + dy)),
      });
    };
    const handleMouseUp = () => {
      setIsDragging(false);
      dragStartRef.current = null;
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, config]);

  if (!open || !product) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <h2 className="font-semibold text-gray-900">Previzualizare Mockup</h2>
            <p className="text-sm text-gray-500">{product.name}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Canvas preview with image navigation */}
            <div className="flex-1 flex flex-col items-center">
              <div
                ref={previewRef}
                className="relative flex items-center justify-center bg-gray-50 rounded-xl p-4 min-h-[350px] w-full cursor-move select-none"
                onMouseDown={handlePreviewMouseDown}
              >
                {generating ? (
                  <div className="flex flex-col items-center gap-3">
                    <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
                    <p className="text-sm text-gray-500">Generare mockup...</p>
                  </div>
                ) : mockupDataUrl ? (
                  <img
                    src={mockupDataUrl}
                    alt="Mockup"
                    className="max-w-full max-h-[400px] object-contain rounded-lg shadow-md"
                    draggable={false}
                  />
                ) : (
                  <p className="text-gray-400 text-sm">Se încarcă...</p>
                )}
                <canvas ref={canvasRef} className="hidden" />

                {/* Image navigation arrows */}
                {allImages.length > 1 && (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); handlePrevImage(); }}
                      onMouseDown={(e) => e.stopPropagation()}
                      className="absolute left-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white shadow-md rounded-full p-1.5 transition-colors z-10"
                    >
                      <ChevronLeft className="w-5 h-5 text-gray-700" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleNextImage(); }}
                      onMouseDown={(e) => e.stopPropagation()}
                      className="absolute right-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white shadow-md rounded-full p-1.5 transition-colors z-10"
                    >
                      <ChevronRight className="w-5 h-5 text-gray-700" />
                    </button>
                  </>
                )}
              </div>

              {/* Image counter */}
              {allImages.length > 1 && (
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-gray-500">
                    Imagine {imageIndex + 1} / {allImages.length}
                  </span>
                  <div className="flex gap-1">
                    {allImages.slice(0, 10).map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setImageIndex(i)}
                        className={`w-2 h-2 rounded-full transition-colors ${
                          i === imageIndex ? "bg-blue-600" : "bg-gray-300"
                        }`}
                      />
                    ))}
                    {allImages.length > 10 && (
                      <span className="text-xs text-gray-400">+{allImages.length - 10}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Drag hint */}
              <p className="text-xs text-gray-400 mt-1">
                Trage logo-ul pe imagine pentru a-l repoziționa
              </p>
            </div>

            {/* Controls */}
            <div className="w-full lg:w-72 space-y-3">
              {/* Print area selector */}
              {product.print_areas.length > 0 && (
                <div>
                  <label className="text-xs font-medium text-gray-600 mb-1 block">
                    Zonă de print
                  </label>
                  <div className="flex flex-wrap gap-1">
                    {product.print_areas.map((pa, i) => (
                      <button
                        key={i}
                        onClick={() => handlePrintAreaChange(i)}
                        className={`px-2 py-1 text-xs rounded-lg border transition-colors ${
                          i === selectedPrintArea
                            ? "border-blue-500 bg-blue-50 text-blue-700"
                            : "border-gray-200 text-gray-600 hover:bg-gray-50"
                        }`}
                      >
                        {pa.location}
                        {pa.width_mm > 0 && pa.height_mm > 0 && (
                          <span className="ml-1 text-[10px] opacity-70">
                            {pa.width_mm}×{pa.height_mm}mm
                          </span>
                        )}
                      </button>
                    ))}
                  </div>

                  {/* Position image from supplier (shows WHERE on product) */}
                  {product.print_areas[selectedPrintArea]?.position_image && (
                    <div className="mt-2 relative">
                      <img
                        src={product.print_areas[selectedPrintArea].position_image}
                        alt={`Zonă: ${product.print_areas[selectedPrintArea].location}`}
                        className="w-full max-h-32 object-contain rounded-lg border border-blue-200 bg-blue-50/50"
                      />
                      <span className="absolute bottom-1 right-1 text-[9px] bg-blue-600 text-white px-1.5 py-0.5 rounded">
                        Zona de personalizare
                      </span>
                    </div>
                  )}

                  {/* Dimensions info */}
                  {product.print_areas[selectedPrintArea] && (
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
                      <span className="font-medium text-gray-700">
                        {product.print_areas[selectedPrintArea].location}
                      </span>
                      {product.print_areas[selectedPrintArea].width_mm > 0 && (
                        <span className="bg-gray-100 px-1.5 py-0.5 rounded text-[10px]">
                          {product.print_areas[selectedPrintArea].width_mm} × {product.print_areas[selectedPrintArea].height_mm} mm
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Position sliders */}
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Poziție X ({config?.x_percent.toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={0}
                  max={80}
                  step={1}
                  value={config?.x_percent ?? 25}
                  onChange={(e) => handleSliderChange("x_percent", +e.target.value)}
                  className="w-full accent-blue-600"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Poziție Y ({config?.y_percent.toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={0}
                  max={80}
                  step={1}
                  value={config?.y_percent ?? 25}
                  onChange={(e) => handleSliderChange("y_percent", +e.target.value)}
                  className="w-full accent-blue-600"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Lățime logo ({config?.width_percent.toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={5}
                  max={80}
                  step={1}
                  value={config?.width_percent ?? 40}
                  onChange={(e) => handleSliderChange("width_percent", +e.target.value)}
                  className="w-full accent-blue-600"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Înălțime logo ({config?.height_percent.toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={5}
                  max={80}
                  step={1}
                  value={config?.height_percent ?? 30}
                  onChange={(e) => handleSliderChange("height_percent", +e.target.value)}
                  className="w-full accent-blue-600"
                />
              </div>

              {/* Rotation control */}
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Rotație logo ({config?.rotation ?? 0}°)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={-180}
                    max={180}
                    step={1}
                    value={config?.rotation ?? 0}
                    onChange={(e) => handleSliderChange("rotation", +e.target.value)}
                    className="flex-1 accent-blue-600"
                  />
                  <button
                    onClick={() => rotateBy(90)}
                    className="p-1.5 hover:bg-gray-100 rounded-lg"
                    title="Rotește 90°"
                  >
                    <RotateCw className="w-4 h-4 text-gray-500" />
                  </button>
                </div>
              </div>

              {/* Warp (curvature) control */}
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Curbură logo
                </label>
                <div className="flex gap-1 mb-1.5">
                  {(["none", "cylinder", "arc"] as WarpMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() =>
                        setConfig(config ? {
                          ...config,
                          warp: mode,
                          warp_intensity: mode !== "none" ? Math.max(config.warp_intensity || 0, 30) : 0,
                        } : null)
                      }
                      className={`flex-1 px-2 py-1 text-[11px] rounded-lg border transition-colors ${
                        config?.warp === mode
                          ? "border-blue-500 bg-blue-50 text-blue-700 font-medium"
                          : "border-gray-200 text-gray-500 hover:bg-gray-50"
                      }`}
                    >
                      {mode === "none" ? "Drept" : mode === "cylinder" ? "Cilindru" : "Arc"}
                    </button>
                  ))}
                </div>
                {config?.warp && config.warp !== "none" && (
                  <div>
                    <label className="text-[10px] text-gray-500 mb-0.5 block">
                      Intensitate ({config.warp_intensity}%)
                    </label>
                    <input
                      type="range"
                      min={5}
                      max={100}
                      step={5}
                      value={config.warp_intensity ?? 50}
                      onChange={(e) => handleSliderChange("warp_intensity" as keyof MockupConfig, +e.target.value)}
                      className="w-full accent-blue-600"
                    />
                  </div>
                )}
              </div>

              {/* Opacity */}
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Opacitate ({((config?.opacity ?? 0.9) * 100).toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={10}
                  max={100}
                  step={5}
                  value={(config?.opacity ?? 0.9) * 100}
                  onChange={(e) => handleSliderChange("opacity", +e.target.value / 100)}
                  className="w-full accent-blue-600"
                />
              </div>

              {/* Blend mode */}
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">
                  Blend Mode
                </label>
                <select
                  value={config?.blend_mode ?? "normal"}
                  onChange={(e) =>
                    setConfig(config ? { ...config, blend_mode: e.target.value } : null)
                  }
                  className="w-full text-sm border border-gray-200 rounded-lg px-2 py-1.5"
                >
                  <option value="multiply">Multiply</option>
                  <option value="screen">Screen</option>
                  <option value="overlay">Overlay</option>
                  <option value="normal">Normal</option>
                </select>
              </div>

              {/* Print method info */}
              {product.print_areas[selectedPrintArea]?.method && (
                <div className="bg-gray-50 rounded-lg px-3 py-2 text-[11px] text-gray-600 border border-gray-100">
                  <span className="font-medium">Metode:</span>{" "}
                  {product.print_areas[selectedPrintArea].method}
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-col gap-2 pt-2">
                <button
                  onClick={handleReset}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset poziție
                </button>
                <button
                  onClick={handleSaveZone}
                  disabled={saving}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <Save className="w-3.5 h-3.5" />
                  {saving ? "Se salvează..." : "Salvează poziția"}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200">
          <button
            onClick={handleDownload}
            disabled={!mockupDataUrl}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Descarcă PNG
          </button>
          <button
            onClick={handleAddToKit}
            disabled={!mockupDataUrl}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            Adaugă în kit
          </button>
        </div>
      </div>
    </div>
  );
}
