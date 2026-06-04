"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FileText,
  Download,
  Loader2,
  ArrowLeft,
  Package,
  Printer,
  CheckCircle2,
  Circle,
  Plus,
  X,
  Trash2,
  StickyNote,
  Camera,
  Pencil,
  Copy,
} from "lucide-react";
import { fetchQuote, confirmQuote, unconfirmQuote, fetchCompanies, updateQuote, updateQuoteItem, addQuoteItem, removeQuoteItem } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Quote, Company } from "@/types";

export default function QuoteDetailPage() {
  const params = useParams();
  const router = useRouter();
  const loadQuoteAsDraft = useStore((s) => s.loadQuoteAsDraft);
  const duplicateQuoteAsDraft = useStore((s) => s.duplicateQuoteAsDraft);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [generatingPDF, setGeneratingPDF] = useState(false);
  const [generatingInternal, setGeneratingInternal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [updatingItems, setUpdatingItems] = useState<Set<string>>(new Set());
  const [companies, setCompanies] = useState<Company[]>([]);

  const [showManualForm, setShowManualForm] = useState(false);
  const [isAddingManual, setIsAddingManual] = useState(false);
  const [manualForm, setManualForm] = useState({
    product_name: "",
    product_sku: "",
    product_color: "",
    product_image: "",
    quantity: 1,
    unit_price: 0,
    margin_percent: 30,
    printing_method: "",
    printing_cost: 0,
    customization_notes: "",
  });

  // Local checked state for item selection
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchCompanies().then(setCompanies).catch(() => {});
  }, []);

  useEffect(() => {
    if (params.id) {
      fetchQuote(String(params.id))
        .then((data) => {
          setQuote(data);
          // Initialize checked items from existing confirmed items
          const confirmed = new Set<string>();
          data.items.forEach((item) => {
            if (item.is_confirmed) confirmed.add(String(item.id));
          });
          setCheckedItems(confirmed);
          setLoading(false);
        })
        .catch(() => {
          setError(true);
          setLoading(false);
        });
    }
  }, [params.id]);

  const handleGeneratePDF = async () => {
    if (!quote) return;
    setGeneratingPDF(true);
    // Open API URL directly so browser gets Content-Disposition header
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "/api";
    window.open(`${apiBase}/quotes/${quote.id}/pdf`, "_blank");
    setTimeout(() => setGeneratingPDF(false), 2000);
  };

  const handleGenerateInternal = async () => {
    if (!quote) return;
    setGeneratingInternal(true);
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "/api";
    window.open(`${apiBase}/quotes/${quote.id}/internal-pdf`, "_blank");
    setTimeout(() => setGeneratingInternal(false), 2000);
  };

  const toggleItem = (itemId: string) => {
    setCheckedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const selectAll = () => {
    if (!quote) return;
    const allIds = quote.items.map((item) => String(item.id));
    setCheckedItems(new Set(allIds));
  };

  const deselectAll = () => {
    setCheckedItems(new Set());
  };

  const isConfirmed = quote?.status === "accepted";

  const handleToggleConfirm = async () => {
    if (!quote) return;
    setSaving(true);
    try {
      if (isConfirmed) {
        // Unconfirm — revert to draft
        const updated = await unconfirmQuote(String(quote.id));
        setQuote(updated);
        setCheckedItems(new Set());
      } else {
        // Confirm with selected items
        const selectedIds = Array.from(checkedItems);
        const updated = await confirmQuote(String(quote.id), selectedIds.length > 0 ? selectedIds : undefined);
        setQuote(updated);
        // Sync checked state from response
        const confirmed = new Set<string>();
        updated.items.forEach((item) => {
          if (item.is_confirmed) confirmed.add(String(item.id));
        });
        setCheckedItems(confirmed);
      }
    } catch {
      // error
    }
    setSaving(false);
  };

  const handleUpdateItem = async (itemId: string, data: Record<string, unknown>) => {
    if (!quote || !itemId) return;
    setUpdatingItems((prev) => new Set(prev).add(itemId));
    try {
      const updated = await updateQuoteItem(String(quote.id), itemId, data as Parameters<typeof updateQuoteItem>[2]);
      setQuote(updated);
    } catch {
      // error
    }
    setUpdatingItems((prev) => {
      const next = new Set(prev);
      next.delete(itemId);
      return next;
    });
  };

  const handleAddManualItem = async () => {
    if (!quote || !manualForm.product_name.trim()) return;
    setIsAddingManual(true);
    try {
      const updated = await addQuoteItem(quote.id, {
        product_name: manualForm.product_name.trim(),
        product_sku: manualForm.product_sku.trim(),
        product_color: manualForm.product_color.trim(),
        product_image: manualForm.product_image.trim(),
        quantity: manualForm.quantity,
        unit_price: manualForm.unit_price,
        margin_percent: manualForm.margin_percent,
        printing_method: manualForm.printing_method.trim(),
        printing_cost: manualForm.printing_cost,
        customization_notes: manualForm.customization_notes.trim(),
      });
      setQuote(updated);
      setManualForm({
        product_name: "",
        product_sku: "",
        product_color: "",
        product_image: "",
        quantity: 1,
        unit_price: 0,
        margin_percent: 30,
        printing_method: "",
        printing_cost: 0,
        customization_notes: "",
      });
      setShowManualForm(false);
    } catch {
      // error
    }
    setIsAddingManual(false);
  };

  const handleRemoveItem = async (itemId: string) => {
    if (!quote || !itemId) return;
    setUpdatingItems((prev) => new Set(prev).add(itemId));
    try {
      const updated = await removeQuoteItem(String(quote.id), itemId);
      setQuote(updated);
    } catch {
      // error
    }
    setUpdatingItems((prev) => {
      const next = new Set(prev);
      next.delete(itemId);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-accent" size={24} />
      </div>
    );
  }

  if (error || !quote) {
    return (
      <div className="p-6 text-center text-red-400">
        Oferta nu a fost găsită.
      </div>
    );
  }

  const statusConfig: Record<string, { label: string; color: string }> = {
    draft: { label: "Ciornă", color: "bg-yellow-500/20 text-yellow-400" },
    sent: { label: "Trimisă", color: "bg-blue-500/20 text-blue-400" },
    accepted: { label: "Comandă fermă", color: "bg-green-500/20 text-green-400" },
    rejected: { label: "Respinsă", color: "bg-red-500/20 text-red-400" },
  };
  const status = statusConfig[quote.status] ?? {
    label: quote.status,
    color: "bg-dark-400/50 text-dark-100",
  };

  const checkedCount = checkedItems.size;
  const totalItems = quote.items.length;

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="max-w-4xl mx-auto space-y-4 sm:space-y-6">
        {/* Back + header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3 sm:gap-4">
            <a
              href="/quotes"
              className="p-2 rounded-xl text-dark-200 hover:text-dark-50 hover:bg-dark-400/30 transition-colors flex-shrink-0"
            >
              <ArrowLeft size={18} />
            </a>
            <div className="min-w-0">
              <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                <h1 className="text-lg sm:text-xl font-bold text-dark-50">
                  Ofertă #{quote.number}
                </h1>
                <span
                  className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${status.color}`}
                >
                  {status.label}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-dark-200 mt-0.5 truncate">
                {quote.client_company || quote.client_name || "Fără client"}
                {quote.created_at &&
                  ` · ${new Date(quote.created_at).toLocaleDateString("ro-RO")}`}
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap pl-11 sm:pl-0">
            <button
              onClick={() => {
                if (!quote) return;
                loadQuoteAsDraft(quote);
                router.push("/chat");
              }}
              className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-xs sm:text-sm font-medium bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 hover:text-amber-200 border border-amber-500/30 transition-all"
              title="Editează în panou ofertă"
            >
              <Pencil size={14} />
              Editează
            </button>
            <button
              onClick={() => {
                if (!quote) return;
                duplicateQuoteAsDraft(quote);
                router.push("/chat");
              }}
              className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-xs sm:text-sm font-medium bg-sky-500/15 text-sky-300 hover:bg-sky-500/25 hover:text-sky-200 border border-sky-500/30 transition-all"
              title="Duplică oferta într-o nouă ciornă (originala rămâne intactă)"
            >
              <Copy size={14} />
              Duplică
            </button>
            <button
              onClick={handleGeneratePDF}
              disabled={generatingPDF}
              className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-xs sm:text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
            >
              {generatingPDF ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Download size={14} />
              )}
              PDF
            </button>
            <button
              onClick={handleGenerateInternal}
              disabled={generatingInternal}
              className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-xs sm:text-sm font-medium bg-dark-400/30 text-dark-100 hover:text-dark-50 hover:bg-dark-400/50 border border-[rgba(255,255,255,0.06)] transition-all disabled:opacity-40"
            >
              {generatingInternal ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <FileText size={14} />
              )}
              Fișă
            </button>
          </div>
        </div>

        {/* Company selector */}
        {companies.length > 0 && (
          <div className="p-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20">
            <h3 className="text-xs text-dark-200 uppercase tracking-wider mb-2">
              Companie ofertantă
            </h3>
            <select
              value={quote.company_id || ""}
              onChange={async (e) => {
                const companyId = e.target.value || null;
                try {
                  const updated = await updateQuote(String(quote.id), {
                    company_id: companyId,
                  });
                  setQuote(updated);
                } catch {
                  // error
                }
              }}
              className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30 appearance-none cursor-pointer"
            >
              <option value="">Fără companie selectată</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.is_default ? " (implicită)" : ""}
                </option>
              ))}
            </select>
            {quote.company_id && (
              <p className="text-[10px] text-dark-300 mt-1.5">
                PDF-ul va fi generat cu datele companiei selectate.
              </p>
            )}
          </div>
        )}

        {/* Comandă fermă toggle bar */}
        <div
          className={`p-4 rounded-2xl border transition-all ${
            isConfirmed
              ? "bg-green-500/5 border-green-500/20"
              : "bg-dark-500/20 border-[rgba(255,255,255,0.06)]"
          }`}
        >
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <CheckCircle2
                size={20}
                className={isConfirmed ? "text-green-400" : "text-dark-300"}
              />
              <div>
                <p className={`text-sm font-semibold ${isConfirmed ? "text-green-400" : "text-dark-100"}`}>
                  Comandă fermă
                </p>
                <p className="text-xs text-dark-300">
                  {isConfirmed
                    ? `${quote.items.filter((i) => i.is_confirmed).length} din ${totalItems} produse confirmate`
                    : checkedCount > 0
                    ? `${checkedCount} din ${totalItems} produse selectate`
                    : "Selectează produsele și confirmă comanda"}
                </p>
              </div>
            </div>

            <button
              onClick={handleToggleConfirm}
              disabled={saving}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all disabled:opacity-50 ml-8 sm:ml-0 ${
                isConfirmed
                  ? "bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20"
                  : "bg-green-500/10 text-green-400 hover:bg-green-500/20 border border-green-500/20"
              }`}
            >
              {saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : isConfirmed ? (
                "Revocă comanda"
              ) : (
                "Confirmă comanda"
              )}
            </button>
          </div>
        </div>

        {/* Client info card */}
        {(quote.client_company || quote.client_name || quote.client_email) && (
          <div className="p-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20">
            <h3 className="text-xs text-dark-200 uppercase tracking-wider mb-2">
              Client
            </h3>
            <div className="space-y-1 text-sm">
              {quote.client_company && (
                <p className="font-medium text-dark-50">
                  {quote.client_company}
                </p>
              )}
              {quote.client_name && quote.client_name.toLowerCase() !== "client" && (
                <p className="text-dark-100">{quote.client_name}</p>
              )}
              {quote.client_email && (
                <p className="text-dark-200">{quote.client_email}</p>
              )}
              {quote.client_phone && (
                <p className="text-dark-200">{quote.client_phone}</p>
              )}
            </div>
          </div>
        )}

        {/* Products table */}
        <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 overflow-hidden">
          <div className="p-4 border-b border-[rgba(255,255,255,0.06)] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-dark-50">
              Produse ({quote.items.length})
            </h3>
            {!isConfirmed && totalItems > 1 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={selectAll}
                  className="text-xs text-dark-200 hover:text-dark-50 transition-colors"
                >
                  Selectează tot
                </button>
                <span className="text-dark-400">|</span>
                <button
                  onClick={deselectAll}
                  className="text-xs text-dark-200 hover:text-dark-50 transition-colors"
                >
                  Deselectează
                </button>
              </div>
            )}
          </div>

          <div className="divide-y divide-[rgba(255,255,255,0.04)]">
            {quote.items.map((item, i) => {
              const itemId = String(item.id);
              const itemChecked = checkedItems.has(itemId);
              const itemConfirmed = isConfirmed && item.is_confirmed;
              const itemNotConfirmed = isConfirmed && !item.is_confirmed;

              return (
                <div
                  key={item.id || i}
                  className={`p-3 sm:p-4 flex flex-col sm:flex-row gap-3 sm:gap-4 transition-all ${
                    itemConfirmed
                      ? "bg-green-500/5"
                      : itemNotConfirmed
                      ? "opacity-40"
                      : ""
                  }`}
                >
                  {/* Top row on mobile: checkbox + image + name */}
                  <div className="flex gap-3 sm:contents">
                  {/* Checkbox / confirmed indicator */}
                  <div className="flex items-start pt-1 flex-shrink-0">
                    {isConfirmed ? (
                      // Show confirmed status (read-only)
                      item.is_confirmed ? (
                        <CheckCircle2 size={20} className="text-green-400" />
                      ) : (
                        <Circle size={20} className="text-dark-400" />
                      )
                    ) : (
                      // Editable checkbox
                      <button
                        onClick={() => toggleItem(itemId)}
                        className={`transition-all ${
                          itemChecked
                            ? "text-green-400"
                            : "text-dark-400 hover:text-dark-200"
                        }`}
                      >
                        {itemChecked ? (
                          <CheckCircle2 size={20} />
                        ) : (
                          <Circle size={20} />
                        )}
                      </button>
                    )}
                  </div>

                  {/* Image — clickable to upload/replace */}
                  <label className="relative group cursor-pointer flex-shrink-0">
                    {item.product_image ? (
                      <img
                        src={item.product_image}
                        alt={item.product_name}
                        className="w-16 h-16 rounded-xl object-contain bg-white/5"
                      />
                    ) : (
                      <div className="w-16 h-16 rounded-xl bg-dark-400/30 flex items-center justify-center">
                        <Package size={20} className="text-dark-300" />
                      </div>
                    )}
                    <div className="absolute inset-0 rounded-xl bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <Camera size={16} className="text-white" />
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        const fd = new FormData();
                        fd.append("file", file);
                        try {
                          const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/settings/upload/product-image`, { method: "POST", body: fd });
                          if (!res.ok) throw new Error();
                          const data = await res.json();
                          await handleUpdateItem(itemId, { product_image: data.url });
                        } catch { /* error */ }
                      }}
                    />
                  </label>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        className="font-medium text-dark-50 text-sm bg-transparent border-b border-transparent hover:border-dark-300 focus:border-blue-400 focus:outline-none w-full sm:max-w-[350px]"
                        defaultValue={item.product_name}
                        onBlur={(e) => {
                          const val = e.target.value.trim();
                          if (val && val !== item.product_name) {
                            handleUpdateItem(item.id!, { product_name: val });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      />
                      {itemConfirmed && (
                        <span className="text-[10px] font-medium bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full">
                          Confirmat
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-dark-200 font-mono mt-0.5">
                      {item.product_sku}
                    </p>
                    <div className="flex flex-wrap gap-2 mt-1.5">
                      {item.product_color && (
                        <span className="text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                          {item.product_color}
                        </span>
                      )}
                      {item.product_size && (
                        <span className="text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                          {item.product_size}
                        </span>
                      )}
                    </div>
                    {/* Editable printing method */}
                    <div className="flex items-center gap-1.5 mt-1">
                      <Printer size={10} className="text-dark-200 flex-shrink-0" />
                      <input
                        type="text"
                        defaultValue={item.printing_method || ""}
                        key={`pm-${itemId}-${item.printing_method}`}
                        placeholder="Personalizare (ex: Tampografie)"
                        onBlur={(e) => {
                          if (e.target.value !== (item.printing_method || "")) {
                            handleUpdateItem(itemId, { printing_method: e.target.value });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                        className="text-[11px] text-dark-100 bg-dark-400/30 rounded px-2 py-0.5 border border-dark-400/40 hover:border-accent/30 focus:border-accent/40 focus:outline-none w-48"
                      />
                    </div>
                    {/* Editable notes */}
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <StickyNote size={10} className="text-dark-200 flex-shrink-0" />
                      <input
                        type="text"
                        defaultValue={item.customization_notes || ""}
                        key={`notes-${itemId}-${item.customization_notes}`}
                        placeholder="Observații (apare pe ofertă)"
                        onBlur={(e) => {
                          if (e.target.value !== (item.customization_notes || "")) {
                            handleUpdateItem(itemId, { customization_notes: e.target.value });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                        className="text-[11px] text-dark-100 bg-dark-400/30 rounded px-2 py-0.5 border border-dark-400/40 hover:border-accent/30 focus:border-accent/40 focus:outline-none w-48"
                      />
                    </div>
                  </div>
                  </div>{/* close mobile top-row wrapper */}

                  {/* Pricing details */}
                  <div className="text-right text-sm flex-shrink-0 space-y-0.5 pl-10 sm:pl-0">
                    <p className="text-dark-200 text-xs">
                      Achiziție: {item.unit_price.toFixed(2)} EUR
                    </p>
                    <div className="flex items-center justify-end gap-1 text-xs">
                      <span className="text-dark-200">Marjă:</span>
                      <input
                        type="number"
                        step="1"
                        min={0}
                        max={200}
                        defaultValue={item.margin_percent}
                        key={`margin-${itemId}-${item.margin_percent}`}
                        onBlur={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val) && val !== item.margin_percent) {
                            handleUpdateItem(itemId, { margin_percent: val });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                        disabled={updatingItems.has(itemId)}
                        className="w-12 text-xs text-dark-50 text-center bg-dark-400/40 rounded px-1 py-0.5 border border-dark-400/60 hover:border-accent/30 focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-dark-200">%</span>
                    </div>
                    <p className="text-dark-100 text-xs">
                      Vânzare: {item.sell_price.toFixed(2)} EUR
                    </p>
                    <div className="flex items-center justify-end gap-1 text-xs">
                      <span className="text-dark-200">Personalizare:</span>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        defaultValue={item.printing_cost || ""}
                        key={`pcost-${itemId}-${item.printing_cost}`}
                        placeholder="0.00"
                        onBlur={(e) => {
                          const val = parseFloat(e.target.value) || 0;
                          if (val !== (item.printing_cost || 0)) {
                            handleUpdateItem(itemId, { printing_cost: val });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                        disabled={updatingItems.has(itemId)}
                        className="w-14 text-xs text-dark-50 text-center bg-dark-400/40 rounded px-1 py-0.5 border border-dark-400/60 hover:border-accent/30 focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-dark-200">RON/buc</span>
                    </div>
                    {(item.printing_setup ?? 0) > 0 && (
                      <p className="text-dark-200 text-xs">
                        Setup: {item.printing_setup!.toFixed(2)} RON
                      </p>
                    )}
                    <div className="flex items-center gap-1 mt-1 font-semibold text-dark-50">
                      <input
                        type="number"
                        min={1}
                        className="w-14 bg-dark-400/30 border border-dark-300 rounded px-1.5 py-0.5 text-sm text-center focus:border-blue-400 focus:outline-none"
                        defaultValue={item.quantity}
                        onBlur={(e) => {
                          const val = parseInt(e.target.value) || 1;
                          if (val !== item.quantity) {
                            handleUpdateItem(item.id!, { quantity: val });
                          }
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      />
                      <span className="text-sm">× {item.sell_price.toFixed(2)} EUR</span>
                    </div>
                    <p className={`font-bold text-base ${itemConfirmed ? "text-green-400" : "text-accent"}`}>
                      {item.total.toFixed(2)} EUR
                    </p>
                    {!isConfirmed && (
                      <button
                        onClick={() => handleRemoveItem(itemId)}
                        disabled={updatingItems.has(itemId)}
                        className="mt-1 text-[10px] text-dark-300 hover:text-red-400 transition-colors flex items-center gap-1 ml-auto"
                      >
                        <Trash2 size={10} />
                        Șterge
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Add manual product */}
          {!isConfirmed && (
            <div className="p-4 border-t border-[rgba(255,255,255,0.04)]">
              {showManualForm ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-accent">Adaugă produs manual</span>
                    <button onClick={() => setShowManualForm(false)} className="text-dark-300 hover:text-dark-50">
                      <X size={14} />
                    </button>
                  </div>

                  <input
                    type="text"
                    placeholder="Nume produs *"
                    value={manualForm.product_name}
                    onChange={(e) => setManualForm((f) => ({ ...f, product_name: e.target.value }))}
                    className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                  />

                  <div className="flex items-center gap-2">
                    <label className="flex-1 flex items-center gap-2 cursor-pointer text-sm text-dark-200 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] hover:border-accent/30 transition-colors">
                      <Package size={14} className="text-dark-300 flex-shrink-0" />
                      <span className="truncate">
                        {manualForm.product_image ? "Imagine încărcată" : "Încarcă imagine produs"}
                      </span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          const fd = new FormData();
                          fd.append("file", file);
                          try {
                            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/settings/upload/product-image`, { method: "POST", body: fd });
                            if (!res.ok) throw new Error();
                            const data = await res.json();
                            setManualForm((f) => ({ ...f, product_image: data.url }));
                          } catch { /* error */ }
                        }}
                      />
                    </label>
                    {manualForm.product_image && (
                      <img src={manualForm.product_image} alt="" className="w-10 h-10 rounded-lg object-contain bg-white/5" />
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      placeholder="SKU / Cod"
                      value={manualForm.product_sku}
                      onChange={(e) => setManualForm((f) => ({ ...f, product_sku: e.target.value }))}
                      className="text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                    />
                    <input
                      type="text"
                      placeholder="Culoare"
                      value={manualForm.product_color}
                      onChange={(e) => setManualForm((f) => ({ ...f, product_color: e.target.value }))}
                      className="text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label className="text-[10px] text-dark-300 block mb-1">Cantitate</label>
                      <input
                        type="number"
                        min={1}
                        value={manualForm.quantity}
                        onChange={(e) => setManualForm((f) => ({ ...f, quantity: parseInt(e.target.value) || 1 }))}
                        className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-dark-300 block mb-1">Preț unit. (EUR)</label>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        value={manualForm.unit_price || ""}
                        onChange={(e) => setManualForm((f) => ({ ...f, unit_price: parseFloat(e.target.value) || 0 }))}
                        className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-dark-300 block mb-1">Marjă (%)</label>
                      <input
                        type="number"
                        step="1"
                        min={0}
                        value={manualForm.margin_percent}
                        onChange={(e) => setManualForm((f) => ({ ...f, margin_percent: parseFloat(e.target.value) || 0 }))}
                        className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] text-dark-300 block mb-1">Personalizare</label>
                      <input
                        type="text"
                        placeholder="ex: Tampografie"
                        value={manualForm.printing_method}
                        onChange={(e) => setManualForm((f) => ({ ...f, printing_method: e.target.value }))}
                        className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-dark-300 block mb-1">Cost pers. (RON/buc)</label>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        value={manualForm.printing_cost || ""}
                        onChange={(e) => setManualForm((f) => ({ ...f, printing_cost: parseFloat(e.target.value) || 0 }))}
                        className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                    </div>
                  </div>

                  <textarea
                    placeholder="Observații (apare pe ofertă)"
                    rows={2}
                    value={manualForm.customization_notes}
                    onChange={(e) => setManualForm((f) => ({ ...f, customization_notes: e.target.value }))}
                    className="w-full text-sm text-dark-50 bg-dark-400/30 rounded-xl px-3 py-2 border border-[rgba(255,255,255,0.06)] focus:border-accent/40 focus:outline-none placeholder:text-dark-300 resize-none"
                  />

                  <button
                    onClick={handleAddManualItem}
                    disabled={isAddingManual || !manualForm.product_name.trim()}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {isAddingManual ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                    Adaugă produs
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowManualForm(true)}
                  className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-dashed border-dark-400/40 text-sm text-dark-200 hover:text-accent hover:border-accent/30 transition-colors"
                >
                  <Plus size={14} />
                  Adaugă produs manual
                </button>
              )}
            </div>
          )}
        </div>

        {/* Totals */}
        <div className={`p-4 rounded-2xl border transition-all ${
          isConfirmed
            ? "border-green-500/20 bg-green-500/5"
            : "border-[rgba(255,255,255,0.06)] bg-dark-500/20"
        }`}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-dark-100">Subtotal</span>
            <span className="text-sm text-dark-100">
              {quote.subtotal.toFixed(2)} EUR
            </span>
          </div>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-[rgba(255,255,255,0.06)]">
            <span className="text-lg font-bold text-dark-50">Total</span>
            <span className={`text-xl font-bold ${isConfirmed ? "text-green-400" : "text-accent"}`}>
              {quote.total.toFixed(2)} EUR
            </span>
          </div>
        </div>

        {/* Notes */}
        {quote.notes && (
          <div className="p-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20">
            <h3 className="text-xs text-dark-200 uppercase tracking-wider mb-2">
              Note interne
            </h3>
            <p className="text-sm text-dark-100">{quote.notes}</p>
          </div>
        )}
      </div>
    </div>
  );
}
