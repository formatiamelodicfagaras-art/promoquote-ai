"use client";

import { useEffect, useRef, useState } from "react";
import { Filter, Zap } from "lucide-react";
import { useProductSearch } from "@/lib/useProductSearch";
import { useStore } from "@/lib/store";
import SearchBar from "@/components/products/SearchBar";
import FilterSidebar from "@/components/products/FilterSidebar";
import ProductGrid from "@/components/products/ProductGrid";
import Pagination from "@/components/products/Pagination";
import SortSelect from "@/components/products/SortSelect";
import type { Product } from "@/types";

export default function ProductsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const {
    results,
    total,
    page,
    totalPages,
    facets,
    allCategories,
    categoryTree,
    colorHexMap,
    processingTimeMs,
    suggestions,
    filters,
    loading,
    error,
    setQuery,
    setFilter,
    clearFilters,
    setPage,
    setSort,
  } = useProductSearch();

  const addToQuote = useStore((s) => s.addToQuote);
  const unifiedCategory = useStore((s) => s.unifiedCategory);
  const unifiedSubcategory = useStore((s) => s.unifiedSubcategory);

  // Sync global unified category state with search filters
  useEffect(() => {
    setFilter("unified_category", unifiedCategory);
    setFilter("unified_subcategory", unifiedSubcategory);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unifiedCategory, unifiedSubcategory]);

  const handleAddToQuote = (product: Product) => {
    addToQuote(product);
  };

  return (
    <div className="flex h-full">
      {/* Filter sidebar */}
      <FilterSidebar
        facets={facets}
        allCategories={allCategories}
        categoryTree={categoryTree}
        filters={filters}
        colorHexMap={colorHexMap}
        onFilterChange={setFilter}
        onClear={clearFilters}
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* Main content */}
      <div ref={contentRef} className="flex-1 min-w-0 p-4 lg:p-6 overflow-y-auto">
        {/* Search bar */}
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2.5 rounded-xl border border-gray-200 text-gray-500 hover:bg-gray-50"
          >
            <Filter className="w-5 h-5" />
          </button>
          <SearchBar
            value={filters.q ?? ""}
            onChange={setQuery}
            suggestions={suggestions}
            loading={loading}
          />
        </div>

        {/* Results bar */}
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3 text-sm text-gray-500">
            <span>
              <strong className="text-gray-900">
                {total.toLocaleString("ro-RO")}
              </strong>{" "}
              produse
            </span>
            {processingTimeMs > 0 && (
              <span className="flex items-center gap-1 text-xs text-gray-400">
                <Zap className="w-3 h-3" />
                {processingTimeMs}ms
              </span>
            )}
          </div>
          <SortSelect
            value={filters.sort ?? ""}
            onChange={setSort}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Product grid */}
        <ProductGrid
          products={results}
          loading={loading && results.length === 0}
          onAddToQuote={handleAddToQuote}
        />

        {/* Pagination */}
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={(p: number) => { setPage(p); contentRef.current?.scrollTo({ top: 0, behavior: "smooth" }); }}
        />
      </div>
    </div>
  );
}
