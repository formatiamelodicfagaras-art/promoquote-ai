"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { UnifiedTree } from "@/types";

interface CategoryMenuBarProps {
  tree: UnifiedTree;
  selectedCategory: string;
  selectedSubcategory: string;
  onSelect: (category: string, subcategory: string) => void;
}

// Order top-level categories logically (most relevant first)
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

export default function CategoryMenuBar({
  tree,
  selectedCategory,
  selectedSubcategory,
  onSelect,
}: CategoryMenuBarProps) {
  const [openCat, setOpenCat] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpenCat(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Sort categories by predefined order, then by total count desc
  const categories = Object.keys(tree).sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return 0;
  });

  const handleSelectSub = (cat: string, sub: string) => {
    onSelect(cat, sub);
    setOpenCat(null);
  };

  const handleSelectAll = (cat: string) => {
    onSelect(cat, "");
    setOpenCat(null);
  };

  const clearSelection = () => {
    onSelect("", "");
    setOpenCat(null);
  };

  return (
    <div ref={containerRef} className="relative bg-white border border-gray-200 rounded-2xl mb-3 shadow-sm">
      <div className="flex items-center gap-1 overflow-x-auto px-2 py-1.5 scrollbar-thin">
        {selectedCategory && (
          <button
            onClick={clearSelection}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-red-600 hover:bg-red-50 flex-shrink-0"
            title="Resetează categoria"
          >
            <X size={14} />
          </button>
        )}
        {categories.map((cat) => {
          const subs = tree[cat] ?? {};
          const total = Object.values(subs).reduce((a, b) => a + b, 0);
          const isOpen = openCat === cat;
          const isActive = selectedCategory === cat;
          return (
            <div key={cat} className="relative flex-shrink-0">
              <button
                onClick={() => setOpenCat(isOpen ? null : cat)}
                className={cn(
                  "flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap",
                  isActive
                    ? "bg-indigo-100 text-indigo-700"
                    : "text-gray-700 hover:bg-gray-100"
                )}
              >
                {cat}
                <span className="text-[10px] text-gray-400">{total.toLocaleString("ro-RO")}</span>
                <ChevronDown
                  size={14}
                  className={cn("transition-transform", isOpen && "rotate-180")}
                />
              </button>

              {isOpen && (
                <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-gray-200 rounded-xl shadow-xl p-2 min-w-[260px] max-h-[60vh] overflow-y-auto">
                  <button
                    onClick={() => handleSelectAll(cat)}
                    className={cn(
                      "w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                      isActive && !selectedSubcategory
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-gray-900 hover:bg-gray-50"
                    )}
                  >
                    Toate ({Object.values(subs).reduce((a, b) => a + b, 0).toLocaleString("ro-RO")})
                  </button>
                  <div className="h-px bg-gray-100 my-1" />
                  {Object.entries(subs)
                    .sort((a, b) => b[1] - a[1])
                    .map(([sub, cnt]) => {
                      const subActive = isActive && selectedSubcategory === sub;
                      return (
                        <button
                          key={sub}
                          onClick={() => handleSelectSub(cat, sub)}
                          className={cn(
                            "w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                            subActive
                              ? "bg-indigo-50 text-indigo-700 font-medium"
                              : "text-gray-700 hover:bg-gray-50"
                          )}
                        >
                          <span>{sub}</span>
                          <span className="text-xs text-gray-400">{cnt.toLocaleString("ro-RO")}</span>
                        </button>
                      );
                    })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
