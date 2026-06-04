"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  ChevronDown,
  ChevronRight,
  Filter,
  X,
  PackageCheck,
} from "lucide-react";
import type { SearchFacets, SearchFilters, CategoryTree } from "@/types";

interface FilterSidebarProps {
  facets: SearchFacets;
  allCategories: Record<string, number>;
  categoryTree: CategoryTree;
  filters: SearchFilters;
  colorHexMap?: Record<string, string>;
  onFilterChange: <K extends keyof SearchFilters>(
    key: K,
    value: SearchFilters[K]
  ) => void;
  onClear: () => void;
  open: boolean;
  onToggle: () => void;
}

const PRICE_RANGES = [
  { label: "Sub 5 €", min: 0, max: 5 },
  { label: "5 – 10 €", min: 5, max: 10 },
  { label: "10 – 25 €", min: 10, max: 25 },
  { label: "25 – 50 €", min: 25, max: 50 },
  { label: "50 – 100 €", min: 50, max: 100 },
  { label: "100 – 250 €", min: 100, max: 250 },
  { label: "250+ €", min: 250, max: undefined },
];

/** Standard hex for each Romanian color group (used in sidebar filter) */
const COLOR_GROUP_HEX: Record<string, string> = {
  Alb: "#FFFFFF",
  Albastru: "#3B82F6",
  Argintiu: "#C0C0C0",
  Auriu: "#FFD700",
  Bej: "#D4A574",
  Bleumarin: "#1B2A4A",
  Bordo: "#800020",
  Coral: "#FF7F50",
  Denim: "#1560BD",
  Galben: "#EAB308",
  Gri: "#6B7280",
  Kaki: "#6B6B37",
  Maro: "#8B4513",
  Mov: "#A855F7",
  Multicolor: "",
  Negru: "#000000",
  Piersica: "#FFAB76",
  Portocaliu: "#F97316",
  Roz: "#EC4899",
  Rosu: "#EF4444",
  Transparent: "",
  Turcoaz: "#06B6D4",
  Verde: "#22C55E",
  Cupru: "#B87333",
  "Galben Neon": "#CCFF00",
  Lavanda: "#B57EDC",
};

export default function FilterSidebar({
  facets,
  allCategories,
  categoryTree,
  filters,
  onFilterChange,
  onClear,
  open,
  onToggle,
}: FilterSidebarProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    category: true,
    price: false,
    color: false,
  });

  // Which supplier is expanded (click to toggle)
  const [expandedSupplier, setExpandedSupplier] = useState<string | null>(null);
  // Which group is hovered (for flyout)
  const [hoveredGroup, setHoveredGroup] = useState<{ supplier: string; group: string } | null>(null);
  const [flyoutPos, setFlyoutPos] = useState({ top: 0, left: 0 });
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, []);

  const toggleSection = (key: string) =>
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));

  const hasActiveFilters =
    !!filters.category ||
    !!filters.subcategory ||
    !!filters.category_group ||
    filters.min_price != null ||
    filters.max_price != null ||
    !!filters.color_group ||
    !!filters.integration_id ||
    filters.in_stock;

  const categoryEntries = Object.entries(allCategories).sort((a, b) => a[0].localeCompare(b[0]));
  const colorGroupEntries = Object.entries(facets.color_groups ?? {}).sort((a, b) =>
    a[0].localeCompare(b[0], "ro")
  );

  const selectedPriceKey =
    filters.min_price != null || filters.max_price != null
      ? `${filters.min_price ?? 0}-${filters.max_price ?? "+"}`
      : null;

  // Click supplier: expand/collapse + filter
  const handleSupplierClick = (name: string) => {
    if (expandedSupplier === name) {
      setExpandedSupplier(null);
      setHoveredGroup(null);
      onFilterChange("category", "");
    } else {
      setExpandedSupplier(name);
      onFilterChange("category", name);
    }
  };

  // Hover on a group row → show flyout
  const handleGroupHoverEnter = useCallback(
    (supplier: string, group: string, el: HTMLElement) => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
      const rect = el.getBoundingClientRect();
      setFlyoutPos({ top: rect.top, left: rect.right + 4 });
      setHoveredGroup({ supplier, group });
    },
    []
  );

  const handleGroupHoverLeave = useCallback(() => {
    hoverTimeoutRef.current = setTimeout(() => setHoveredGroup(null), 150);
  }, []);

  const handleFlyoutEnter = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
  }, []);

  const handleFlyoutLeave = useCallback(() => {
    setHoveredGroup(null);
  }, []);

  // Get subcategories for hovered group
  const flyoutSubs =
    hoveredGroup
      ? Object.entries(
          categoryTree[hoveredGroup.supplier]?.[hoveredGroup.group] ?? {}
        ).sort((a, b) => b[1] - a[1])
      : [];

  // Compute group totals for display
  const getGroupTotal = (supplier: string, group: string) => {
    const subs = categoryTree[supplier]?.[group] ?? {};
    return Object.values(subs).reduce((s, c) => s + c, 0);
  };

  // Check if group has only 1 sub that matches the group name (MIDOCEAN case)
  const isSingleSubGroup = (supplier: string, group: string) => {
    const subs = Object.keys(categoryTree[supplier]?.[group] ?? {});
    return subs.length === 1 && subs[0] === group;
  };

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-40 h-full w-72 bg-white border-r border-gray-200 overflow-y-auto
          transform transition-transform duration-200 ease-out
          lg:static lg:translate-x-0 lg:z-auto lg:shrink-0
          ${open ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <span className="font-semibold text-sm">Filtre</span>
          </div>
          <div className="flex items-center gap-2">
            {hasActiveFilters && (
              <button
                onClick={() => {
                  setExpandedSupplier(null);
                  setHoveredGroup(null);
                  onClear();
                }}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Resetează
              </button>
            )}
            <button onClick={onToggle} className="lg:hidden">
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </div>

        {/* In stock toggle */}
        <div className="px-4 py-3 border-b border-gray-100">
          <label className="flex items-center gap-2.5 cursor-pointer">
            <div className="relative">
              <input
                type="checkbox"
                checked={filters.in_stock ?? false}
                onChange={(e) => onFilterChange("in_stock", e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 peer-checked:bg-blue-500 rounded-full transition-colors" />
              <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow peer-checked:translate-x-4 transition-transform" />
            </div>
            <PackageCheck className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-700">Doar în stoc</span>
          </label>
        </div>

        {/* ── Suppliers with groups inline ── */}
        {categoryEntries.length > 0 && (
          <FilterSection
            title="Furnizor / Categorie"
            expanded={expandedSections.category}
            onToggle={() => toggleSection("category")}
          >
            <div className="space-y-0.5">
              {categoryEntries.map(([name, count]) => {
                const isExpanded = expandedSupplier === name;
                const groups = categoryTree[name] ?? {};
                const groupEntries = Object.entries(groups).sort(
                  (a, b) => getGroupTotal(name, b[0]) - getGroupTotal(name, a[0])
                );

                return (
                  <div key={name}>
                    {/* Supplier row */}
                    <button
                      onClick={() => handleSupplierClick(name)}
                      className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-sm transition-colors ${
                        isExpanded
                          ? "bg-blue-50 text-blue-700 font-semibold"
                          : "text-gray-700 hover:bg-gray-50 font-medium"
                      }`}
                    >
                      <span className="flex items-center gap-1.5">
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                        )}
                        {name}
                      </span>
                      <span className="text-xs text-gray-400 ml-2 shrink-0">
                        {count.toLocaleString("ro-RO")}
                      </span>
                    </button>

                    {/* Groups inline (expanded on click) */}
                    {isExpanded && groupEntries.length > 0 && (
                      <div className="ml-4 mt-1 mb-2 border-l-2 border-blue-100 pl-2 max-h-[50vh] overflow-y-auto">
                        {groupEntries.map(([groupName]) => {
                          const total = getGroupTotal(name, groupName);
                          const singleSub = isSingleSubGroup(name, groupName);

                          return (
                            <div
                              key={groupName}
                              onMouseEnter={(e) => {
                                if (!singleSub) {
                                  handleGroupHoverEnter(name, groupName, e.currentTarget);
                                }
                              }}
                              onMouseLeave={handleGroupHoverLeave}
                            >
                              <button
                                onClick={() => {
                                  if (singleSub) {
                                    onFilterChange(
                                      "subcategory",
                                      filters.subcategory === groupName ? "" : groupName
                                    );
                                  } else {
                                    // Toggle category_group filter
                                    onFilterChange(
                                      "category_group",
                                      filters.category_group === groupName ? "" : groupName
                                    );
                                  }
                                }}
                                className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-xs transition-colors ${
                                  filters.category_group === groupName ||
                                  (filters.subcategory &&
                                  Object.keys(categoryTree[name]?.[groupName] ?? {}).includes(filters.subcategory))
                                    ? "bg-blue-50 text-blue-700 font-medium"
                                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                                }`}
                              >
                                <span className="flex items-center gap-1 truncate pr-1">
                                  {!singleSub && (
                                    <ChevronRight className={`w-3 h-3 shrink-0 ${
                                      hoveredGroup?.group === groupName && hoveredGroup?.supplier === name
                                        ? "text-blue-500"
                                        : "text-gray-300"
                                    }`} />
                                  )}
                                  <span className="truncate uppercase text-[10px] font-semibold tracking-wide">
                                    {groupName}
                                  </span>
                                </span>
                                <span className="text-[10px] text-gray-400 shrink-0 ml-1">
                                  {total.toLocaleString("ro-RO")}
                                </span>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Active category_group chip */}
            {filters.category_group && (
              <div className="mt-2 pt-2 border-t border-gray-100">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] text-gray-400 uppercase tracking-wider">Categorie:</span>
                  <button
                    onClick={() => onFilterChange("category_group", "")}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs font-medium hover:bg-blue-100 transition-colors"
                  >
                    {filters.category_group}
                    <X className="w-3 h-3" />
                  </button>
                </div>
              </div>
            )}

            {/* Active subcategory chip */}
            {filters.subcategory && (
              <div className="mt-2 pt-2 border-t border-gray-100">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] text-gray-400 uppercase tracking-wider">Subcategorie:</span>
                  <button
                    onClick={() => onFilterChange("subcategory", "")}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs font-medium hover:bg-blue-100 transition-colors"
                  >
                    {filters.subcategory}
                    <X className="w-3 h-3" />
                  </button>
                </div>
              </div>
            )}
          </FilterSection>
        )}

        {/* ── Price ranges ── */}
        <FilterSection
          title="Preț"
          expanded={expandedSections.price}
          onToggle={() => toggleSection("price")}
        >
          <div className="space-y-0.5">
            {PRICE_RANGES.map((range) => {
              const key = `${range.min}-${range.max ?? "+"}`;
              const active = selectedPriceKey === key;
              return (
                <button
                  key={key}
                  onClick={() => {
                    if (active) {
                      onFilterChange("min_price", undefined);
                      onFilterChange("max_price", undefined);
                    } else {
                      onFilterChange("min_price", range.min || undefined);
                      onFilterChange("max_price", range.max);
                    }
                  }}
                  className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors ${
                    active
                      ? "bg-blue-50 text-blue-700 font-medium"
                      : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {range.label}
                </button>
              );
            })}
          </div>
        </FilterSection>

        {/* ── Colors (standard Romanian groups) ── */}
        {colorGroupEntries.length > 0 && (
          <FilterSection
            title="Culoare"
            expanded={expandedSections.color}
            onToggle={() => toggleSection("color")}
          >
            <div className="flex flex-wrap gap-2">
              {colorGroupEntries.map(([name, count]) => {
                const hex = COLOR_GROUP_HEX[name] ?? "";
                const active = filters.color_group === name;
                return (
                  <button
                    key={name}
                    onClick={() => onFilterChange("color_group", active ? "" : name)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors ${
                      active
                        ? "border-blue-400 bg-blue-50 text-blue-700"
                        : "border-gray-200 hover:border-gray-300 text-gray-600"
                    }`}
                    title={`${name} (${count})`}
                  >
                    {name === "Multicolor" ? (
                      <span
                        className="w-3 h-3 rounded-full border border-gray-200 shrink-0"
                        style={{
                          backgroundImage:
                            "conic-gradient(#EF4444, #EAB308, #22C55E, #3B82F6, #A855F7, #EF4444)",
                        }}
                      />
                    ) : hex ? (
                      <span
                        className="w-3 h-3 rounded-full border border-gray-200 shrink-0"
                        style={{ backgroundColor: hex }}
                      />
                    ) : null}
                    <span>{name}</span>
                  </button>
                );
              })}
            </div>
          </FilterSection>
        )}

        <div className="h-8" />
      </aside>

      {/* ── Subcategory flyout (portal) ── */}
      {mounted &&
        hoveredGroup &&
        flyoutSubs.length > 0 &&
        createPortal(
          <div
            onMouseEnter={handleFlyoutEnter}
            onMouseLeave={handleFlyoutLeave}
            className="fixed bg-white border border-gray-200 rounded-xl shadow-2xl z-[9999] overflow-hidden"
            style={{
              top: Math.min(flyoutPos.top, (typeof window !== "undefined" ? window.innerHeight : 800) - 400),
              left: flyoutPos.left,
              width: "300px",
              maxHeight: "60vh",
            }}
          >
            {/* Flyout header */}
            <div className="px-4 py-2 bg-gradient-to-r from-blue-50 to-white border-b border-gray-100 sticky top-0">
              <span className="font-semibold text-xs text-blue-700 uppercase tracking-wide">
                {hoveredGroup.group}
              </span>
            </div>

            {/* Subcategory list */}
            <div className="overflow-y-auto py-1" style={{ maxHeight: "calc(60vh - 36px)" }}>
              {flyoutSubs.map(([subName, subCount]) => {
                const isActive = filters.subcategory === subName;
                return (
                  <button
                    key={subName}
                    onClick={() => {
                      onFilterChange("subcategory", isActive ? "" : subName);
                      setHoveredGroup(null);
                    }}
                    className={`w-full flex items-center justify-between px-4 py-1.5 text-left text-xs transition-colors ${
                      isActive
                        ? "bg-blue-50 text-blue-700 font-medium"
                        : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                    }`}
                  >
                    <span className="truncate pr-2">{subName}</span>
                    <span className="text-[10px] text-gray-400 shrink-0">
                      {subCount.toLocaleString("ro-RO")}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}

function FilterSection({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-gray-100">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        {title}
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {expanded && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}
