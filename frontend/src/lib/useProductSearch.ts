"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useDebouncedCallback } from "use-debounce";
import { searchProducts, getSuggestions, getCategoryTree, getUnifiedTree } from "./api";
import type { SuggestionItem } from "./api";
import type { SearchResponse, SearchFilters, SearchFacets, CategoryTree, UnifiedTree } from "@/types";

interface UseProductSearchReturn {
  // Data
  results: SearchResponse["results"];
  total: number;
  page: number;
  totalPages: number;
  facets: SearchFacets;
  /** Category facets from unfiltered state (all suppliers always visible) */
  allCategories: Record<string, number>;
  /** Full category tree: supplier -> { subcategory: count } */
  categoryTree: CategoryTree;
  /** Unified taxonomy tree: cat -> { subcat: count } */
  unifiedTree: UnifiedTree;
  colorHexMap: Record<string, string>;
  processingTimeMs: number;
  suggestions: SuggestionItem[];

  // State
  filters: SearchFilters;
  loading: boolean;
  error: string | null;

  // Actions
  setQuery: (q: string) => void;
  setFilter: <K extends keyof SearchFilters>(
    key: K,
    value: SearchFilters[K]
  ) => void;
  setFilters: (f: Partial<SearchFilters>) => void;
  clearFilters: () => void;
  setPage: (page: number) => void;
  setSort: (sort: string) => void;
  refresh: () => void;
}

const DEFAULT_FILTERS: SearchFilters = {
  q: "",
  category: "",
  subcategory: "",
  category_group: "",
  unified_category: "",
  unified_subcategory: "",
  color: "",
  color_group: "",
  integration_id: "",
  in_stock: false,
  sort: "",
  page: 1,
  limit: 40,
  group_variants: true,
};

export function useProductSearch(): UseProductSearchReturn {
  const [filters, setFiltersState] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [results, setResults] = useState<SearchResponse["results"]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPageState] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [facets, setFacets] = useState<SearchFacets>({});
  const [allCategories, setAllCategories] = useState<Record<string, number>>({});
  const [categoryTree, setCategoryTree] = useState<CategoryTree>({});
  const [unifiedTree, setUnifiedTree] = useState<UnifiedTree>({});
  const [colorHexMap, setColorHexMap] = useState<Record<string, string>>({});
  const [processingTimeMs, setProcessingTimeMs] = useState(0);
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const doSearch = useCallback(async (f: SearchFilters) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const data = await searchProducts(f);
      if (controller.signal.aborted) return;
      setResults(data.results);
      setTotal(data.total);
      setPageState(data.page);
      setTotalPages(data.total_pages);
      setFacets(data.facets ?? {});
      setColorHexMap(data.color_hex_map ?? {});
      setProcessingTimeMs(data.processing_time_ms);

      // Cache category (supplier) facets from unfiltered results
      // so all suppliers stay visible even when one is selected
      const cats = data.facets?.category ?? {};
      if (!f.category && Object.keys(cats).length > 0) {
        setAllCategories(cats);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  const debouncedSearch = useDebouncedCallback((f: SearchFilters) => {
    doSearch(f);
  }, 150);

  const fetchSuggestions = useDebouncedCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    const s = await getSuggestions(q);
    setSuggestions(s);
  }, 100);

  // Run search when filters change
  useEffect(() => {
    debouncedSearch(filters);
  }, [filters, debouncedSearch]);

  // Initial load
  useEffect(() => {
    doSearch(DEFAULT_FILTERS);
    getCategoryTree().then(setCategoryTree).catch(() => {});
    getUnifiedTree().then(setUnifiedTree).catch(() => {});
  }, [doSearch]);

  const setQuery = useCallback(
    (q: string) => {
      setFiltersState((prev) => ({ ...prev, q, page: 1 }));
      fetchSuggestions(q);
    },
    [fetchSuggestions]
  );

  const setFilter = useCallback(
    <K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) => {
      setFiltersState((prev) => {
        const next = { ...prev, [key]: value, page: 1 };
        // Reset subcategory and category_group when category (supplier) changes
        if (key === "category") {
          next.subcategory = "";
          next.category_group = "";
        }
        // Reset subcategory when category_group changes
        if (key === "category_group") {
          next.subcategory = "";
        }
        // Reset unified_subcategory when unified_category changes
        if (key === "unified_category") {
          next.unified_subcategory = "";
        }
        return next;
      });
    },
    []
  );

  const setFiltersPartial = useCallback((f: Partial<SearchFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...f, page: 1 }));
  }, []);

  const clearFilters = useCallback(() => {
    setFiltersState(DEFAULT_FILTERS);
    setSuggestions([]);
  }, []);

  const setPage = useCallback((p: number) => {
    setFiltersState((prev) => ({ ...prev, page: p }));
  }, []);

  const setSort = useCallback((sort: string) => {
    setFiltersState((prev) => ({ ...prev, sort, page: 1 }));
  }, []);

  const refresh = useCallback(() => {
    doSearch(filters);
  }, [doSearch, filters]);

  return {
    results,
    total,
    page,
    totalPages,
    facets,
    allCategories,
    categoryTree,
    unifiedTree,
    colorHexMap,
    processingTimeMs,
    suggestions,
    filters,
    loading,
    error,
    setQuery,
    setFilter,
    setFilters: setFiltersPartial,
    clearFilters,
    setPage,
    setSort,
    refresh,
  };
}
