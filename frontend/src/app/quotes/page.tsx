"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchQuotes } from "@/lib/api";
import QuoteFolders from "@/components/quotes/QuoteFolders";
import { Search, X } from "lucide-react";
import type { Quote } from "@/types";

export default function QuotesPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetchQuotes().then((data) => {
      setQuotes(data);
      setLoading(false);
    });
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return quotes;
    return quotes.filter((quote) => {
      const haystack = [
        quote.number,
        quote.client_name,
        quote.client_company,
        quote.company_name,
        quote.client_email,
        ...(quote.items || []).map((it) => it.product_name),
        ...(quote.items || []).map((it) => it.product_sku),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [quotes, query]);

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="flex items-center justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold">Oferte</h1>
        <a href="/chat" className="btn-primary">
          + Ofertă nouă
        </a>
      </div>

      {/* Search */}
      <div className="relative mb-4 sm:mb-6">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-300 pointer-events-none"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Caută după client, companie, număr ofertă sau produs…"
          className="w-full bg-dark-500/30 border border-[rgba(255,255,255,0.08)] focus:border-accent/40 rounded-xl pl-9 pr-9 py-2.5 text-sm text-dark-50 placeholder:text-dark-300 outline-none transition-all"
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-md text-dark-300 hover:text-dark-50 hover:bg-dark-400/30 transition-colors"
            title="Șterge căutarea"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Se încarcă...</div>
      ) : quotes.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-dark-200">Nu ai nicio ofertă încă.</p>
          <a href="/chat" className="text-accent hover:underline mt-2 inline-block">
            Creează prima ofertă cu AI
          </a>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-dark-200">
          Nicio ofertă nu corespunde căutării.
        </div>
      ) : (
        <QuoteFolders
          quotes={filtered}
          searchActive={query.trim().length > 0}
          onDelete={(id) => setQuotes((prev) => prev.filter((q) => q.id !== id))}
          onUpdate={(updated) =>
            setQuotes((prev) =>
              prev.map((q) => (q.id === updated.id ? updated : q))
            )
          }
        />
      )}
    </div>
  );
}
