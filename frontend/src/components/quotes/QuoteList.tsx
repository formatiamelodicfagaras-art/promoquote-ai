"use client";

import { useState } from "react";
import Link from "next/link";
import { Trash2, Loader2, CheckCircle2 } from "lucide-react";
import { deleteQuote, confirmQuote, unconfirmQuote } from "@/lib/api";
import type { Quote } from "@/types";

interface QuoteListProps {
  quotes: Quote[];
  onDelete?: (id: string) => void;
  onUpdate?: (quote: Quote) => void;
}

export default function QuoteList({ quotes, onDelete, onUpdate }: QuoteListProps) {
  const [deleting, setDeleting] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  if (quotes.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-dark-200">Nu ai nicio ofertă încă.</p>
        <a href="/chat" className="text-accent hover:underline mt-2 inline-block">
          Creează prima ofertă cu AI
        </a>
      </div>
    );
  }

  const handleDelete = async (e: React.MouseEvent, quoteId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Sigur vrei să ștergi această ofertă?")) return;

    setDeleting(quoteId);
    try {
      await deleteQuote(quoteId);
      onDelete?.(quoteId);
    } catch {
      // handle error
    }
    setDeleting(null);
  };

  const handleToggleConfirm = async (e: React.MouseEvent, quote: Quote) => {
    e.preventDefault();
    e.stopPropagation();
    const quoteId = quote.id as string;
    setToggling(quoteId);
    try {
      if (quote.status === "accepted") {
        const updated = await unconfirmQuote(quoteId);
        onUpdate?.(updated);
      } else {
        const updated = await confirmQuote(quoteId);
        onUpdate?.(updated);
      }
    } catch {
      // handle error
    }
    setToggling(null);
  };

  const statusLabels: Record<string, string> = {
    draft: "Ciornă",
    sent: "Trimisă",
    accepted: "Comandă fermă",
    rejected: "Respinsă",
    expired: "Expirată",
  };

  return (
    <div className="space-y-2">
      {quotes.map((quote) => {
        const isConfirmed = quote.status === "accepted";
        return (
          <Link
            key={quote.id}
            href={`/quotes/${quote.id}`}
            className={`flex flex-col sm:flex-row sm:items-center justify-between p-3 sm:p-4 rounded-xl border transition-all group gap-2 sm:gap-0 ${
              isConfirmed
                ? "bg-green-500/5 border-green-500/20 hover:border-green-500/40"
                : "bg-dark-500/20 border-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.12)]"
            }`}
          >
            <div className="flex items-center gap-3">
              {/* Confirm toggle */}
              <button
                onClick={(e) => handleToggleConfirm(e, quote)}
                disabled={toggling === quote.id}
                className={`p-1.5 rounded-lg transition-all flex-shrink-0 ${
                  isConfirmed
                    ? "text-green-400 bg-green-500/10 hover:bg-green-500/20"
                    : "text-dark-300 hover:text-dark-100 hover:bg-dark-400/30"
                }`}
                title={isConfirmed ? "Revocă comanda" : "Marchează comandă fermă"}
              >
                {toggling === quote.id ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <CheckCircle2 size={18} />
                )}
              </button>

              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-semibold text-dark-50 text-sm">
                    {quote.number}
                  </span>
                  {quote.company_name && (
                    <span className="text-[11px] text-dark-200 font-medium">
                      {quote.company_name}
                    </span>
                  )}
                </div>
                <p className="text-xs text-dark-200 mt-0.5 truncate">
                  {quote.client_company ||
                    (quote.client_name &&
                    quote.client_name.toLowerCase() !== "client"
                      ? quote.client_name
                      : "Fără client")}{" "}
                  — {quote.items.length} produse
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 justify-between sm:justify-end pl-10 sm:pl-0">
              <div className="text-left sm:text-right">
                <p className={`font-bold text-sm ${isConfirmed ? "text-green-400" : "text-accent"}`}>
                  {quote.total.toFixed(2)} {quote.currency}
                </p>
                <p className="text-[10px] text-dark-300">
                  {quote.created_at
                    ? new Date(quote.created_at).toLocaleDateString("ro-RO")
                    : ""}
                </p>
              </div>
              <button
                onClick={(e) => handleDelete(e, quote.id as string)}
                disabled={deleting === quote.id}
                className="sm:opacity-0 sm:group-hover:opacity-100 p-1.5 rounded-lg text-dark-300 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-50"
                title="Șterge oferta"
              >
                {deleting === quote.id ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Trash2 size={14} />
                )}
              </button>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
