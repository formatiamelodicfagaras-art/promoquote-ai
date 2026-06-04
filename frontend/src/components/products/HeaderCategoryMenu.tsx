"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { LucideIcon } from "lucide-react";
import { createPortal } from "react-dom";
import {
  ChevronDown,
  X,
  Shirt,
  PenTool,
  Coffee,
  Briefcase,
  Smartphone,
  ChefHat,
  Dumbbell,
  KeyRound,
  Umbrella,
  Baby,
  Heart,
  Gift,
  Car,
  Package,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import { getUnifiedTree } from "@/lib/api";
import type { UnifiedTree } from "@/types";

const CATEGORY_ORDER = [
  "Textile",
  "Pixuri si Birou",
  "Drinkware",
  "Genti si Calatorie",
  "Tehnologie",
  "Casa si Bucatarie",
  "Sport si Outdoor",
  "Brelocuri si Cadouri mici",
  "Umbrele",
  "Copii si Jocuri",
  "Sanatate si Frumusete",
  "Evenimente si Craciun",
  "Auto si Siguranta",
  "Diverse",
];

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  "Textile": Shirt,
  "Pixuri si Birou": PenTool,
  "Drinkware": Coffee,
  "Genti si Calatorie": Briefcase,
  "Tehnologie": Smartphone,
  "Casa si Bucatarie": ChefHat,
  "Sport si Outdoor": Dumbbell,
  "Brelocuri si Cadouri mici": KeyRound,
  "Umbrele": Umbrella,
  "Copii si Jocuri": Baby,
  "Sanatate si Frumusete": Heart,
  "Evenimente si Craciun": Gift,
  "Auto si Siguranta": Car,
  "Diverse": Package,
};

// Per-category accent color (single hex used for icon + active state)
const CATEGORY_ACCENT: Record<string, string> = {
  "Textile": "#3b82f6",                  // blue
  "Pixuri si Birou": "#f59e0b",          // amber
  "Drinkware": "#f97316",                // orange
  "Genti si Calatorie": "#10b981",       // emerald
  "Tehnologie": "#06b6d4",               // cyan
  "Casa si Bucatarie": "#f43f5e",        // rose
  "Sport si Outdoor": "#84cc16",         // lime
  "Brelocuri si Cadouri mici": "#8b5cf6",// violet
  "Umbrele": "#0ea5e9",                  // sky
  "Copii si Jocuri": "#ec4899",          // pink
  "Sanatate si Frumusete": "#d946ef",    // fuchsia
  "Evenimente si Craciun": "#ef4444",    // red
  "Auto si Siguranta": "#eab308",        // yellow
  "Diverse": "#64748b",                  // slate
};

const DEFAULT_ACCENT = "#6b7280";

interface DropdownState {
  cat: string;
  left: number;
  top: number;
}

export default function HeaderCategoryMenu() {
  const [tree, setTree] = useState<UnifiedTree>({});
  const [dropdown, setDropdown] = useState<DropdownState | null>(null);
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const unifiedCategory = useStore((s) => s.unifiedCategory);
  const unifiedSubcategory = useStore((s) => s.unifiedSubcategory);
  const setUnifiedCategory = useStore((s) => s.setUnifiedCategory);

  useEffect(() => {
    setMounted(true);
    getUnifiedTree().then(setTree).catch(() => {});
  }, []);

  const close = useCallback(() => setDropdown(null), []);

  useEffect(() => {
    if (!dropdown) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Element;
      if (target.closest("[data-cat-menu]")) return;
      close();
    };
    document.addEventListener("mousedown", handler);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", handler);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [dropdown, close]);

  const categories = Object.keys(tree).sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return 0;
  });

  const toggleDropdown = (cat: string, btn: HTMLButtonElement) => {
    if (dropdown?.cat === cat) {
      close();
      return;
    }
    const rect = btn.getBoundingClientRect();
    setDropdown({ cat, left: rect.left, top: rect.bottom + 4 });
  };

  const handleSelect = (cat: string, sub: string) => {
    setUnifiedCategory(cat, sub);
    close();
  };

  const dropdownSubs = dropdown ? tree[dropdown.cat] ?? {} : {};
  const dropdownTotal = Object.values(dropdownSubs).reduce((a, b) => a + b, 0);

  return (
    <>
      <div ref={containerRef} className="flex items-center gap-1 min-w-0 flex-1 overflow-hidden" data-cat-menu>
        {unifiedCategory && (
          <button
            onClick={() => setUnifiedCategory("", "")}
            className="flex items-center justify-center w-6 h-6 rounded-md text-red-400 bg-red-500/10 hover:bg-red-500/20 hover:text-red-300 flex-shrink-0 mr-1 border border-red-500/30"
            title="Resetează filtrul"
          >
            <X size={12} strokeWidth={3} />
          </button>
        )}
        <div className="flex md:grid md:grid-cols-5 gap-1 min-w-0 flex-1 overflow-x-auto scrollbar-hide pb-0.5">
          {categories.map((cat) => {
            const subs = tree[cat] ?? {};
            const total = Object.values(subs).reduce((a, b) => a + b, 0);
            const isOpen = dropdown?.cat === cat;
            const isActive = unifiedCategory === cat;
            const Icon = CATEGORY_ICONS[cat] ?? Package;
            const accent = CATEGORY_ACCENT[cat] ?? DEFAULT_ACCENT;
            const highlighted = isActive || isOpen;
            return (
              <button
                key={cat}
                onClick={(e) => toggleDropdown(cat, e.currentTarget)}
                style={
                  highlighted
                    ? {
                        backgroundColor: "#ffffff",
                        boxShadow: `0 0 0 2px ${accent}, 0 4px 12px -2px rgba(0,0,0,0.4)`,
                        color: "#0f172a",
                      }
                    : undefined
                }
                className={cn(
                  "group flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap border",
                  !highlighted &&
                    "border-slate-700/60 bg-slate-800/60 text-slate-200 hover:bg-slate-700/80 hover:border-slate-600 hover:text-white"
                )}
              >
                <span
                  className="flex items-center justify-center w-5 h-5 rounded-md flex-shrink-0"
                  style={{ backgroundColor: `${accent}33`, color: accent }}
                >
                  <Icon size={12} strokeWidth={2.5} />
                </span>
                <span className="truncate flex-1 text-left">{cat}</span>
                <span
                  className="text-[10px] flex-shrink-0 font-mono"
                  style={{ color: highlighted ? "#64748b" : "#94a3b8" }}
                >
                  {total >= 1000 ? `${(total / 1000).toFixed(1)}k` : total}
                </span>
                <ChevronDown
                  size={12}
                  className={cn(
                    "transition-transform flex-shrink-0",
                    isOpen && "rotate-180",
                    highlighted ? "opacity-70" : "opacity-50"
                  )}
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* Portal dropdown — escapes header overflow */}
      {mounted && dropdown && createPortal(
        <div
          data-cat-menu
          style={{ position: "fixed", left: dropdown.left, top: dropdown.top }}
          className="z-[100] bg-white border border-gray-200 rounded-xl shadow-2xl p-2 min-w-[280px] max-h-[70vh] overflow-y-auto"
        >
          <div className="flex items-center gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide">
            {(() => {
              const Icon = CATEGORY_ICONS[dropdown.cat] ?? Package;
              const accent = CATEGORY_ACCENT[dropdown.cat] ?? DEFAULT_ACCENT;
              return (
                <>
                  <span
                    className="flex items-center justify-center w-5 h-5 rounded-md"
                    style={{ backgroundColor: `${accent}33`, color: accent }}
                  >
                    <Icon size={12} strokeWidth={2.5} />
                  </span>
                  <span className="text-gray-700">{dropdown.cat}</span>
                </>
              );
            })()}
          </div>
          <button
            onClick={() => handleSelect(dropdown.cat, "")}
            className={cn(
              "w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors",
              unifiedCategory === dropdown.cat && !unifiedSubcategory
                ? "bg-indigo-100 text-indigo-700"
                : "text-gray-900 hover:bg-gray-100"
            )}
          >
            Toate ({dropdownTotal.toLocaleString("ro-RO")})
          </button>
          <div className="h-px bg-gray-200 my-1" />
          {Object.entries(dropdownSubs)
            .sort((a, b) => b[1] - a[1])
            .map(([sub, cnt]) => {
              const subActive = unifiedCategory === dropdown.cat && unifiedSubcategory === sub;
              return (
                <button
                  key={sub}
                  onClick={() => handleSelect(dropdown.cat, sub)}
                  className={cn(
                    "w-full flex items-center justify-between gap-3 px-3 py-1.5 rounded-lg text-xs transition-colors",
                    subActive
                      ? "bg-indigo-100 text-indigo-700 font-medium"
                      : "text-gray-700 hover:bg-gray-100"
                  )}
                >
                  <span>{sub}</span>
                  <span className="text-[10px] text-gray-400">{cnt.toLocaleString("ro-RO")}</span>
                </button>
              );
            })}
        </div>,
        document.body
      )}
    </>
  );
}
