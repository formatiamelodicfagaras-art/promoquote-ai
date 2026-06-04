"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Download,
  Mail,
  X,
  Trash2,
  Plus,
  Minus,
  Package,
  Loader2,
  Printer,
  StickyNote,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import type { DraftItem } from "@/lib/store";
import {
  generateInternalPDF,
  removeQuoteItem,
  updateQuoteItem,
  updateQuote,
  fetchSettings,
  fetchCompanies,
  addQuoteItem,
  createQuote,
} from "@/lib/api";
import type { Company } from "@/types";
import ClientAutocomplete from "./ClientAutocomplete";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

/** Try to re-host a Makito image via our backend upload */
async function tryUploadExternalImage(url: string): Promise<string> {
  if (!url || !url.includes("makito.es")) return url;
  try {
    const resp = await fetch(url);
    if (!resp.ok) return url;
    const blob = await resp.blob();
    const fd = new FormData();
    fd.append("file", blob, "product.jpg");
    const up = await fetch(`${API}/settings/upload/product-image`, {
      method: "POST",
      body: fd,
    });
    if (!up.ok) return url;
    const data = await up.json();
    return data.url || url;
  } catch {
    return url;
  }
}

export default function QuotePanel() {
  const {
    currentQuote,
    isQuotePanelOpen,
    toggleQuotePanel,
    setCurrentQuote,
    draftItems,
    draftNumber,
    draftClientName,
    draftClientCompany,
    draftClientEmail,
    draftCompanyId,
    updateDraftItem,
    setDraftClient,
    clearDraft,
    removeFromQuote,
  } = useStore();

  const setDraftNumber = useStore((s) => s.setDraftNumber);
  const setDraftClientName = useStore((s) => s.setDraftClientName);
  const setDraftClientCompany = useStore((s) => s.setDraftClientCompany);
  const setDraftClientEmail = useStore((s) => s.setDraftClientEmail);
  const setDraftCompanyId = useStore((s) => s.setDraftCompanyId);

  const [isGeneratingPDF, setIsGeneratingPDF] = useState(false);
  const [isGeneratingInternal, setIsGeneratingInternal] = useState(false);
  const [updatingItems, setUpdatingItems] = useState<Set<string>>(new Set());
  const [exchangeRate, setExchangeRate] = useState(4.97);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [showManualForm, setShowManualForm] = useState(false);
  const [isAddingManual, setIsAddingManual] = useState(false);
  // Aliases — read directly from Zustand store (persists across navigation)
  const localNumber = draftNumber;
  const localClientName = draftClientName;
  const localClientCompany = draftClientCompany;
  const localClientEmail = draftClientEmail;
  const localCompanyId = draftCompanyId;
  const setLocalNumber = setDraftNumber;
  const setLocalClientName = setDraftClientName;
  const setLocalClientCompany = setDraftClientCompany;
  const setLocalClientEmail = setDraftClientEmail;
  const setLocalCompanyId = setDraftCompanyId;
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

  useEffect(() => {
    Promise.all([fetchSettings(), fetchCompanies()])
      .then(([settings, companiesData]) => {
        const rateSetting = settings.find(
          (s) => s.key === "exchange_rate_eur_ron"
        );
        if (rateSetting) {
          const val = parseFloat(rateSetting.value);
          if (!isNaN(val) && val > 0) setExchangeRate(val);
        }
        setCompanies(companiesData);
      })
      .catch(() => {});
  }, []);

  const isDraftMode = draftItems.length > 0;
  const isSavedMode = !isDraftMode && !!currentQuote;

  // Panel not visible if nothing to show
  if (!isQuotePanelOpen || (!isDraftMode && !currentQuote)) return null;

  // ── Draft mode helpers ──────────────────────────────────────────────

  const calcDraftItemTotal = (d: DraftItem) => {
    // If size-quantities are set, compute per-size using size_prices
    if (d.size_quantities && d.size_quantities.length > 0 && d.size_prices) {
      const margin = (d.margin_percent || 0) / 100;
      let subtotal = 0;
      let totalQty = 0;
      for (const sq of d.size_quantities) {
        if (!sq.qty) continue;
        const sp = d.size_prices.find((p) => p.size === sq.size);
        const unit = sp ? sp.price : d.unit_price;
        const sell = unit * (1 + margin);
        subtotal += (sell * exchangeRate + d.printing_cost) * sq.qty;
        totalQty += sq.qty;
      }
      return subtotal + (totalQty > 0 ? d.printing_setup : 0);
    }
    return (d.sell_price * exchangeRate + d.printing_cost) * d.quantity +
      d.printing_setup;
  };

  const draftTotal = isDraftMode
    ? draftItems.reduce((sum, d) => sum + calcDraftItemTotal(d), 0)
    : 0;

  const handleDraftRemove = (index: number) => {
    removeFromQuote(index);
  };

  const handleDraftQuantity = (localId: string, delta: number) => {
    const item = draftItems.find((d) => d.localId === localId);
    if (!item) return;
    const newQty = Math.max(1, item.quantity + delta);
    updateDraftItem(localId, { quantity: newQty });
  };

  const handleDraftQuantitySet = (localId: string, val: number) => {
    if (val >= 1) updateDraftItem(localId, { quantity: val });
  };

  const handleAddManualDraft = () => {
    if (!manualForm.product_name.trim()) return;
    const sellPrice =
      manualForm.unit_price * (1 + manualForm.margin_percent / 100);
    const draft: DraftItem = {
      localId: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      product_name: manualForm.product_name.trim(),
      product_sku: manualForm.product_sku.trim(),
      product_color: manualForm.product_color.trim(),
      product_size: "",
      product_image: manualForm.product_image.trim(),
      quantity: manualForm.quantity,
      unit_price: manualForm.unit_price,
      margin_percent: manualForm.margin_percent,
      sell_price: Math.round(sellPrice * 100) / 100,
      printing_method: manualForm.printing_method.trim(),
      printing_cost: manualForm.printing_cost,
      printing_setup: 0,
      customization_notes: manualForm.customization_notes.trim(),
      colors: [],
    };
    useStore.setState((state) => ({
      draftItems: [...state.draftItems, draft],
    }));
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
  };

  // ── Generate PDF (draft mode): create quote + add items + download ──
  const handleGeneratePDFDraft = async () => {
    // If the manual product form is open with a valid name, commit it first
    // so users don't lose data they typed but didn't explicitly "add".
    if (showManualForm && manualForm.product_name.trim()) {
      handleAddManualDraft();
    }

    // Read draft items from store (these change as user adds/removes), but
    // use local state for client info / number (avoids reactivity issues)
    const liveDraftItems = useStore.getState().draftItems;

    if (liveDraftItems.length === 0) return;
    setIsGeneratingPDF(true);
    try {
      // 1. Re-host Makito images
      const resolvedImages = await Promise.all(
        liveDraftItems.map((d) => tryUploadExternalImage(d.product_image))
      );

      // 2. Determine quote number + company
      const quoteNumber = localNumber.trim() || `PQ-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
      const defaultCompany = companies.find((c) => c.is_default);
      const companyId = localCompanyId || defaultCompany?.id || null;
      const editingId = useStore.getState().editingQuoteId;

      // 3. If editing AND the number is being kept, we need to free it up first.
      // We do this by temporarily renaming the old quote so the new one can take the number.
      // The old one will be deleted ONLY after the new one is successfully created.
      if (editingId) {
        try {
          await fetch(`${API}/quotes/${editingId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ number: `__editing__${editingId}` }),
          });
        } catch (err) {
          console.warn("Failed to rename original quote:", err);
        }
      }

      // 4. Create quote in DB
      let quote;
      try {
        quote = await createQuote({
          number: quoteNumber,
          client_name: localClientName,
          client_company: localClientCompany,
          client_email: localClientEmail,
          company_id: companyId,
          status: "draft",
        } as Parameters<typeof createQuote>[0]);
      } catch (createErr) {
        // Restore old quote number if create fails
        if (editingId) {
          try {
            await fetch(`${API}/quotes/${editingId}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ number: quoteNumber }),
            });
          } catch {
            // ignore
          }
        }
        throw createErr;
      }

      // 5. Add items sequentially
      let savedQuote = quote;
      for (let i = 0; i < liveDraftItems.length; i++) {
        const d = liveDraftItems[i];
        const hasSizeBreakdown = d.size_quantities && d.size_quantities.length > 0
          && d.size_quantities.some((sq) => sq.qty > 0);
        const effectiveQty = hasSizeBreakdown
          ? d.size_quantities!.reduce((s, sq) => s + (sq.qty || 0), 0)
          : d.quantity;
        savedQuote = await addQuoteItem(quote.id, {
          product_id: d.product_id,
          product_name: d.product_name,
          product_sku: d.product_sku,
          product_color: d.product_color,
          product_image: resolvedImages[i],
          product_size: d.product_size,
          quantity: effectiveQty,
          unit_price: d.unit_price,
          margin_percent: d.margin_percent,
          printing_method: d.printing_method || undefined,
          printing_cost: d.printing_cost || undefined,
          printing_setup: d.printing_setup || undefined,
          customization_notes: d.customization_notes || undefined,
          size_quantities: hasSizeBreakdown ? d.size_quantities : undefined,
        });
      }

      // 6. New quote saved successfully — NOW delete the old one (if editing)
      if (editingId) {
        try {
          await fetch(`${API}/quotes/${editingId}`, { method: "DELETE" });
        } catch (err) {
          console.warn("Failed to delete old quote after edit:", err);
        }
      }

      // 7. Download PDF
      const res = await fetch(`${API}/quotes/${savedQuote.id}/pdf`);
      if (!res.ok) throw new Error("Failed to generate PDF");
      const cd = res.headers.get("content-disposition") || "";
      let filename = `oferta-${savedQuote.number || savedQuote.id}.pdf`;
      const match = cd.match(/filename\*?=(?:UTF-8'')?([^;\s]+)/i);
      if (match) filename = decodeURIComponent(match[1]);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);

      // 8. Set saved quote + clear draft
      setCurrentQuote(savedQuote);
      clearDraft();
    } catch (err) {
      console.error("Generate PDF error:", err);
      const msg = err instanceof Error ? err.message : "Eroare necunoscută";
      alert(`Nu s-a putut genera oferta: ${msg}`);
    }
    setIsGeneratingPDF(false);
  };

  // ── Saved-quote handlers (existing behavior) ───────────────────────

  const handleGeneratePDF = async () => {
    if (!currentQuote) return;
    setIsGeneratingPDF(true);
    try {
      const res = await fetch(`${API}/quotes/${currentQuote.id}/pdf`);
      if (!res.ok) throw new Error("Failed");
      const cd = res.headers.get("content-disposition") || "";
      let filename = `oferta-${currentQuote.number || currentQuote.id}.pdf`;
      const match = cd.match(/filename\*?=(?:UTF-8'')?([^;\s]+)/i);
      if (match) filename = decodeURIComponent(match[1]);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // toast error
    }
    setIsGeneratingPDF(false);
  };

  const handleGenerateInternal = async () => {
    if (!currentQuote) return;
    setIsGeneratingInternal(true);
    try {
      const blob = await generateInternalPDF(currentQuote.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `comanda-${currentQuote.number || currentQuote.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // toast error
    }
    setIsGeneratingInternal(false);
  };

  const handleRemoveItem = async (itemId: string) => {
    if (!itemId || !currentQuote) return;
    setUpdatingItems((prev) => new Set(prev).add(itemId));
    try {
      const updated = await removeQuoteItem(currentQuote.id, itemId);
      setCurrentQuote(updated);
    } catch {
      // handle error
    }
    setUpdatingItems((prev) => {
      const next = new Set(prev);
      next.delete(itemId);
      return next;
    });
  };

  const handleUpdateQuantity = async (itemId: string, newQuantity: number) => {
    if (!itemId || newQuantity < 1 || !currentQuote) return;
    setUpdatingItems((prev) => new Set(prev).add(itemId));
    try {
      const updated = await updateQuoteItem(currentQuote.id, itemId, {
        quantity: newQuantity,
      });
      setCurrentQuote(updated);
    } catch {
      // handle error
    }
    setUpdatingItems((prev) => {
      const next = new Set(prev);
      next.delete(itemId);
      return next;
    });
  };

  const handleUpdateItem = async (
    itemId: string,
    data: Record<string, unknown>
  ) => {
    if (!itemId || !currentQuote) return;
    setUpdatingItems((prev) => new Set(prev).add(itemId));
    try {
      const updated = await updateQuoteItem(
        currentQuote.id,
        itemId,
        data as Parameters<typeof updateQuoteItem>[2]
      );
      setCurrentQuote(updated);
    } catch {
      // handle error
    }
    setUpdatingItems((prev) => {
      const next = new Set(prev);
      next.delete(itemId);
      return next;
    });
  };

  const handleUpdateQuote = async (data: Record<string, string>) => {
    if (!currentQuote) return;
    try {
      const updated = await updateQuote(currentQuote.id, data);
      setCurrentQuote(updated);
    } catch {
      // handle error
    }
  };

  const handleAddManualItem = async () => {
    if (!currentQuote || !manualForm.product_name.trim()) return;
    setIsAddingManual(true);
    try {
      const updated = await addQuoteItem(currentQuote.id, {
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
      setCurrentQuote(updated);
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
      // handle error
    }
    setIsAddingManual(false);
  };

  const statusConfig: Record<string, { label: string; color: string }> = {
    draft: { label: "Ciorna", color: "bg-yellow-500/20 text-yellow-400" },
    sent: { label: "Trimisa", color: "bg-blue-500/20 text-blue-400" },
    accepted: { label: "Acceptata", color: "bg-green-500/20 text-green-400" },
    rejected: { label: "Respinsa", color: "bg-red-500/20 text-red-400" },
  };

  // ════════════════════════════════════════════════════════════════════
  //  RENDER: DRAFT MODE
  // ════════════════════════════════════════════════════════════════════
  if (isDraftMode) {
    return (
      <motion.div
        initial={{ width: 0, opacity: 0 }}
        animate={{ width: 360, opacity: 1 }}
        exit={{ width: 0, opacity: 0 }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="h-full flex flex-col border-r border-[rgba(255,255,255,0.06)] bg-dark-600/50 backdrop-blur-sm overflow-hidden flex-shrink-0 fixed inset-0 z-50 md:static md:z-auto !w-full md:!w-auto"
      >
        {/* Header */}
        <div className="p-3 border-b border-[rgba(255,255,255,0.06)]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-accent/10 flex items-center justify-center">
                <FileText size={16} className="text-accent" />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <h3 className="text-sm font-semibold text-dark-50">Oferta</h3>
                  <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-orange-500/20 text-orange-400">
                    Draft
                  </span>
                </div>
                <p className="text-[10px] font-mono text-dark-300">
                  {draftItems.length} produs{draftItems.length !== 1 ? "e" : ""}
                </p>
              </div>
            </div>
            <button
              onClick={toggleQuotePanel}
              className="p-1 rounded-lg text-dark-200 hover:text-dark-50 hover:bg-dark-400/30 transition-colors"
            >
              <X size={14} />
            </button>
          </div>

          {/* Quote number */}
          <div className="mt-2">
            <input
              type="text"
              value={localNumber}
              onChange={(e) => setLocalNumber(e.target.value)}
              placeholder="Număr ofertă (ex: PQ-001)"
              className="w-full text-xs bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-lg px-3 py-1.5 text-dark-50 placeholder:text-dark-300 outline-none focus:border-accent/30 font-mono"
            />
          </div>

          {/* Company selector */}
          {companies.length > 0 && (
            <div className="mt-2">
              <select
                value={localCompanyId}
                onChange={(e) => setLocalCompanyId(e.target.value)}
                className="w-full text-[11px] bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-lg px-2 py-1.5 text-dark-50 outline-none focus:border-accent/30 appearance-none cursor-pointer"
              >
                <option value="">Selecteaza compania</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.is_default ? " (implicita)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Client info */}
          <div className="mt-2 p-2.5 rounded-xl bg-dark-400/20 text-xs space-y-1">
            <ClientAutocomplete
              field="client_name"
              value={localClientName}
              onChange={setLocalClientName}
              onPick={(s) => {
                setLocalClientName(s.client_name);
                setLocalClientCompany(s.client_company);
                setLocalClientEmail(s.client_email);
              }}
              placeholder="Nume client"
              className="w-full font-medium text-dark-50 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
            />
            <ClientAutocomplete
              field="client_company"
              value={localClientCompany}
              onChange={setLocalClientCompany}
              onPick={(s) => {
                setLocalClientName(s.client_name);
                setLocalClientCompany(s.client_company);
                setLocalClientEmail(s.client_email);
              }}
              placeholder="Companie"
              className="w-full text-dark-200 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
            />
            <ClientAutocomplete
              field="client_email"
              value={localClientEmail}
              onChange={setLocalClientEmail}
              onPick={(s) => {
                setLocalClientName(s.client_name);
                setLocalClientCompany(s.client_company);
                setLocalClientEmail(s.client_email);
              }}
              placeholder="Email client"
              className="w-full text-dark-200 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
            />
          </div>
        </div>

        {/* Draft Items */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          <AnimatePresence mode="popLayout">
            {draftItems.map((item, index) => (
              <motion.div
                key={item.localId}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                layout
                className="group p-3 rounded-xl bg-dark-500/30 border border-[rgba(255,255,255,0.04)] hover:border-[rgba(255,255,255,0.08)] transition-all"
              >
                {/* Product image + name + delete */}
                <div className="flex items-start gap-2">
                  {item.product_image && (
                    <img
                      src={item.product_image}
                      alt={item.product_name}
                      className="w-12 h-12 rounded-lg object-contain bg-white/5 flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-dark-50 truncate">
                      {item.product_name}
                    </p>
                    <p className="text-[10px] text-dark-200 font-mono mt-0.5">
                      {item.product_sku}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDraftRemove(index)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-dark-200 hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>

                {/* Color tag */}
                {item.product_color && (
                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    <span className="inline-flex items-center gap-1 text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                      <span
                        className="w-2.5 h-2.5 rounded-full border border-white/10"
                        style={{
                          backgroundColor:
                            item.colors?.find(
                              (c) => c.name === item.product_color
                            )?.hex || "#888",
                        }}
                      />
                      {item.product_color}
                    </span>
                    {item.product_size && (
                      <span className="text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                        {item.product_size}
                      </span>
                    )}
                  </div>
                )}

                {/* Printing / customization */}
                <div className="mt-1.5 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Printer
                      size={10}
                      className="text-dark-300 flex-shrink-0"
                    />
                    <input
                      type="text"
                      placeholder="Personalizare (ex: Tampografie)"
                      value={item.printing_method}
                      onChange={(e) =>
                        updateDraftItem(item.localId, {
                          printing_method: e.target.value,
                        })
                      }
                      className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                    />
                  </div>
                  <div className="flex items-center gap-1.5 pl-4">
                    <span className="text-[10px] text-dark-300 whitespace-nowrap">
                      RON/buc:
                    </span>
                    <input
                      type="number"
                      step="0.01"
                      min={0}
                      placeholder="0.00"
                      value={item.printing_cost || ""}
                      onChange={(e) =>
                        updateDraftItem(item.localId, {
                          printing_cost: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-16 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                  </div>
                  <div className="flex items-start gap-1.5">
                    <StickyNote
                      size={10}
                      className="text-orange-400/60 flex-shrink-0 mt-1.5"
                    />
                    <textarea
                      placeholder="Observatii (apare pe oferta)"
                      rows={2}
                      value={item.customization_notes}
                      onChange={(e) =>
                        updateDraftItem(item.localId, {
                          customization_notes: e.target.value,
                        })
                      }
                      className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-dark-400/60 focus:border-accent/40 focus:outline-none placeholder:text-dark-300/70 resize-none"
                    />
                  </div>
                </div>

                {/* Size breakdown toggle (textile only) */}
                {item.size_prices && item.size_prices.length > 1 && (
                  <div className="mt-2">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={
                          !!(item.size_quantities && item.size_quantities.length > 0)
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            const sq = item.size_prices!.map((sp) => ({
                              size: sp.size,
                              qty: 0,
                            }));
                            updateDraftItem(item.localId, { size_quantities: sq });
                          } else {
                            updateDraftItem(item.localId, { size_quantities: [] });
                          }
                        }}
                        className="w-3 h-3 rounded accent-accent"
                      />
                      <span className="text-[10px] text-dark-200">
                        Detaliaza pe marimi
                      </span>
                    </label>
                    {item.size_quantities && item.size_quantities.length > 0 && (
                      <div className="mt-1.5 grid grid-cols-4 gap-1">
                        {item.size_quantities.map((sq, idx) => (
                          <div key={sq.size} className="flex flex-col items-center">
                            <span className="text-[9px] text-dark-300 font-medium">
                              {sq.size}
                            </span>
                            <input
                              type="number"
                              min={0}
                              value={sq.qty || ""}
                              placeholder="0"
                              onChange={(e) => {
                                const val = parseInt(e.target.value, 10) || 0;
                                const updated = [...item.size_quantities!];
                                updated[idx] = { ...updated[idx], qty: val };
                                updateDraftItem(item.localId, {
                                  size_quantities: updated,
                                });
                              }}
                              className="w-full text-[10px] text-dark-50 text-center bg-dark-400/40 rounded px-0.5 py-0.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                            />
                            <span className="text-[9px] text-dark-400">
                              {(item.size_prices!.find((p) => p.size === sq.size)?.price || 0).toFixed(2)}€
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Quantity controls + price */}
                <div className="flex items-center justify-between mt-2">
                  {!(item.size_quantities && item.size_quantities.length > 0) ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleDraftQuantity(item.localId, -1)}
                        disabled={item.quantity <= 1}
                        className="w-6 h-6 rounded-md bg-dark-400/40 flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-400/60 transition-colors disabled:opacity-30"
                      >
                        <Minus size={10} />
                      </button>
                      <input
                        type="number"
                        min={1}
                        value={item.quantity}
                        onChange={(e) => {
                          const val = parseInt(e.target.value, 10);
                          if (!isNaN(val) && val >= 1)
                            handleDraftQuantitySet(item.localId, val);
                        }}
                        className="w-14 text-xs font-medium text-dark-50 text-center bg-dark-400/40 rounded-md px-1 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <button
                        onClick={() => handleDraftQuantity(item.localId, 1)}
                        className="w-6 h-6 rounded-md bg-dark-400/40 flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-400/60 transition-colors"
                      >
                        <Plus size={10} />
                      </button>
                      <span className="text-[10px] text-dark-200 ml-1">
                        x{" "}
                        {(
                          item.sell_price * exchangeRate +
                          item.printing_cost
                        ).toFixed(2)}{" "}
                        RON
                      </span>
                    </div>
                  ) : (
                    <span className="text-[10px] text-dark-200">
                      {item.size_quantities.reduce((s, sq) => s + (sq.qty || 0), 0)} buc. total
                    </span>
                  )}
                  <p className="text-sm font-semibold text-dark-50">
                    {calcDraftItemTotal(item).toFixed(2)}
                  </p>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Manual add product form (draft mode) */}
          <AnimatePresence>
            {showManualForm ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="p-3 rounded-xl bg-dark-500/30 border border-accent/20 space-y-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] font-medium text-accent">
                    Produs manual
                  </span>
                  <button
                    onClick={() => setShowManualForm(false)}
                    className="p-0.5 rounded text-dark-200 hover:text-dark-50"
                  >
                    <X size={12} />
                  </button>
                </div>

                <input
                  type="text"
                  placeholder="Nume produs *"
                  value={manualForm.product_name}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      product_name: e.target.value,
                    }))
                  }
                  className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                />

                <div className="flex items-center gap-1.5">
                  <label className="flex-1 flex items-center gap-1.5 cursor-pointer text-[11px] text-dark-200 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent hover:border-accent/30 transition-colors">
                    <Package
                      size={10}
                      className="text-dark-300 flex-shrink-0"
                    />
                    <span className="truncate">
                      {manualForm.product_image
                        ? "Imagine incarcata"
                        : "Incarca imagine produs"}
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
                          const res = await fetch(
                            `${API}/settings/upload/product-image`,
                            { method: "POST", body: fd }
                          );
                          if (!res.ok) throw new Error();
                          const data = await res.json();
                          setManualForm((f) => ({
                            ...f,
                            product_image: data.url,
                          }));
                        } catch {
                          /* error */
                        }
                      }}
                    />
                  </label>
                  {manualForm.product_image && (
                    <img
                      src={manualForm.product_image}
                      alt=""
                      className="w-8 h-8 rounded object-contain bg-white/5"
                    />
                  )}
                </div>

                <div className="grid grid-cols-2 gap-1.5">
                  <input
                    type="text"
                    placeholder="SKU / Cod"
                    value={manualForm.product_sku}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        product_sku: e.target.value,
                      }))
                    }
                    className="text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                  />
                  <input
                    type="text"
                    placeholder="Culoare"
                    value={manualForm.product_color}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        product_color: e.target.value,
                      }))
                    }
                    className="text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                  />
                </div>

                <div className="grid grid-cols-3 gap-1.5">
                  <div>
                    <label className="text-[9px] text-dark-300 block mb-0.5">
                      Cantitate
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={manualForm.quantity}
                      onChange={(e) =>
                        setManualForm((f) => ({
                          ...f,
                          quantity: parseInt(e.target.value) || 1,
                        }))
                      }
                      className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                  </div>
                  <div>
                    <label className="text-[9px] text-dark-300 block mb-0.5">
                      Pret unit (EUR)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min={0}
                      value={manualForm.unit_price || ""}
                      onChange={(e) =>
                        setManualForm((f) => ({
                          ...f,
                          unit_price: parseFloat(e.target.value) || 0,
                        }))
                      }
                      className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                  </div>
                  <div>
                    <label className="text-[9px] text-dark-300 block mb-0.5">
                      Marja (%)
                    </label>
                    <input
                      type="number"
                      step="1"
                      min={0}
                      value={manualForm.margin_percent}
                      onChange={(e) =>
                        setManualForm((f) => ({
                          ...f,
                          margin_percent: parseFloat(e.target.value) || 0,
                        }))
                      }
                      className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <Printer size={10} className="text-dark-300 flex-shrink-0" />
                  <input
                    type="text"
                    placeholder="Personalizare (ex: Tampografie)"
                    value={manualForm.printing_method}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        printing_method: e.target.value,
                      }))
                    }
                    className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                  />
                </div>
                <div className="flex items-center gap-1.5 pl-4">
                  <span className="text-[10px] text-dark-300 whitespace-nowrap">
                    RON/buc:
                  </span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={manualForm.printing_cost || ""}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        printing_cost: parseFloat(e.target.value) || 0,
                      }))
                    }
                    className="w-16 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                </div>

                <textarea
                  placeholder="Observatii (apare pe oferta)"
                  rows={2}
                  value={manualForm.customization_notes}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      customization_notes: e.target.value,
                    }))
                  }
                  className="w-full text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-dark-400/60 focus:border-accent/40 focus:outline-none placeholder:text-dark-300/70 resize-none"
                />

                <button
                  onClick={handleAddManualDraft}
                  disabled={!manualForm.product_name.trim()}
                  className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus size={12} />
                  Adauga produs
                </button>
              </motion.div>
            ) : (
              <motion.button
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                onClick={() => setShowManualForm(true)}
                className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-dark-400/40 text-[11px] text-dark-200 hover:text-accent hover:border-accent/30 transition-colors"
              >
                <Plus size={12} />
                Adauga produs manual
              </motion.button>
            )}
          </AnimatePresence>
        </div>

        {/* Footer — draft mode */}
        <div className="p-3 border-t border-[rgba(255,255,255,0.06)]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-dark-100">Total</span>
            <span className="text-xl font-bold text-dark-50">
              {draftTotal.toFixed(2)}{" "}
              <span className="text-xs font-normal text-dark-200">RON</span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleGeneratePDFDraft}
              disabled={isGeneratingPDF || draftItems.length === 0}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium text-sm transition-all",
                "bg-success text-white hover:brightness-110 active:scale-[0.98] glow-success",
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
              )}
            >
              {isGeneratingPDF ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Download size={16} />
              )}
              {isGeneratingPDF ? "Se genereaza..." : "Genereaza PDF"}
            </button>
          </div>
        </div>
      </motion.div>
    );
  }

  // ════════════════════════════════════════════════════════════════════
  //  RENDER: SAVED QUOTE MODE (existing behavior)
  // ════════════════════════════════════════════════════════════════════
  if (!currentQuote) return null;

  const status = statusConfig[currentQuote.status] ?? {
    label: currentQuote.status,
    color: "bg-dark-400/50 text-dark-100",
  };

  return (
    <motion.div
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: 360, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ type: "spring", damping: 25, stiffness: 200 }}
      className="h-full flex flex-col border-r border-[rgba(255,255,255,0.06)] bg-dark-600/50 backdrop-blur-sm overflow-hidden flex-shrink-0 fixed inset-0 z-50 md:static md:z-auto !w-full md:!w-auto"
    >
      {/* Header */}
      <div className="p-3 border-b border-[rgba(255,255,255,0.06)]">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-accent/10 flex items-center justify-center">
              <FileText size={16} className="text-accent" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-dark-50">Oferta</h3>
              <input
                type="text"
                defaultValue={currentQuote.number || ""}
                key={`nr-${currentQuote.id}`}
                placeholder="Nr. oferta"
                onBlur={(e) => {
                  if (e.target.value !== (currentQuote.number || "")) {
                    handleUpdateQuote({ number: e.target.value });
                  }
                }}
                className="text-[10px] font-mono text-dark-200 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none w-full py-0.5"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-[10px] font-medium px-2 py-0.5 rounded-full",
                status.color
              )}
            >
              {status.label}
            </span>
            <button
              onClick={toggleQuotePanel}
              className="p-1 rounded-lg text-dark-200 hover:text-dark-50 hover:bg-dark-400/30 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Company selector */}
        {companies.length > 0 && (
          <div className="mt-2">
            <select
              value={currentQuote.company_id || ""}
              onChange={(e) => {
                const val = e.target.value || null;
                handleUpdateQuote({
                  company_id: val,
                } as Record<string, string>);
              }}
              className="w-full text-[11px] bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-lg px-2 py-1.5 text-dark-50 outline-none focus:border-accent/30 appearance-none cursor-pointer"
            >
              <option value="">Selecteaza compania</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.is_default ? " (implicita)" : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Client info — editable */}
        <SavedQuoteClientFields
          key={`client-${currentQuote.id}`}
          initialName={currentQuote.client_name || ""}
          initialCompany={currentQuote.client_company || ""}
          initialEmail={currentQuote.client_email || ""}
          onCommit={(patch) => handleUpdateQuote(patch)}
        />
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        <AnimatePresence mode="popLayout">
          {currentQuote.items.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-10"
            >
              <Package size={32} className="mx-auto text-dark-300 mb-3" />
              <p className="text-sm text-dark-200">Niciun produs adaugat</p>
              <p className="text-xs text-dark-300 mt-1">
                Cere AI-ului sa creeze o oferta
              </p>
            </motion.div>
          ) : (
            currentQuote.items.map((item) => {
              const itemId = item.id ?? "";
              const isUpdating = updatingItems.has(itemId);

              return (
                <motion.div
                  key={itemId || item.product_name}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: isUpdating ? 0.6 : 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  layout
                  className="group p-3 rounded-xl bg-dark-500/30 border border-[rgba(255,255,255,0.04)] hover:border-[rgba(255,255,255,0.08)] transition-all"
                >
                  {/* Product image + name + delete */}
                  <div className="flex items-start gap-2">
                    {item.product_image && (
                      <img
                        src={item.product_image}
                        alt={item.product_name}
                        className="w-12 h-12 rounded-lg object-contain bg-white/5 flex-shrink-0"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-dark-50 truncate">
                        {item.product_name}
                      </p>
                      <p className="text-[10px] text-dark-200 font-mono mt-0.5">
                        {item.product_sku}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRemoveItem(itemId)}
                      disabled={isUpdating}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-dark-200 hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>

                  {/* Color & size tags */}
                  {(item.product_color || item.product_size) && (
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                      {item.product_color && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                          <span
                            className="w-2.5 h-2.5 rounded-full border border-white/10"
                            style={{ backgroundColor: "#888" }}
                          />
                          {item.product_color}
                        </span>
                      )}
                      {item.product_size && (
                        <span className="text-[10px] text-dark-100 bg-dark-400/40 px-1.5 py-0.5 rounded-md">
                          {item.product_size}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Printing / customization */}
                  <div className="mt-1.5 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Printer
                        size={10}
                        className="text-dark-300 flex-shrink-0"
                      />
                      <input
                        type="text"
                        placeholder="Personalizare (ex: Tampografie)"
                        defaultValue={item.printing_method || ""}
                        onBlur={(e) => {
                          if (
                            e.target.value !== (item.printing_method || "")
                          ) {
                            handleUpdateItem(itemId, {
                              printing_method: e.target.value,
                            });
                          }
                        }}
                        disabled={isUpdating}
                        className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                      />
                    </div>
                    <div className="flex items-center gap-1.5 pl-4">
                      <span className="text-[10px] text-dark-300 whitespace-nowrap">
                        RON/buc:
                      </span>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        placeholder="0.00"
                        defaultValue={item.printing_cost || ""}
                        onBlur={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) {
                            handleUpdateItem(itemId, { printing_cost: val });
                          }
                        }}
                        disabled={isUpdating}
                        className="w-16 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                    </div>
                    <div className="flex items-start gap-1.5">
                      <StickyNote
                        size={10}
                        className="text-orange-400/60 flex-shrink-0 mt-1.5"
                      />
                      <textarea
                        placeholder="Observatii (apare pe oferta)"
                        rows={2}
                        defaultValue={item.customization_notes || ""}
                        onBlur={(e) => {
                          if (
                            e.target.value !==
                            (item.customization_notes || "")
                          ) {
                            handleUpdateItem(itemId, {
                              customization_notes: e.target.value,
                            });
                          }
                        }}
                        disabled={isUpdating}
                        className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-dark-400/60 focus:border-accent/40 focus:outline-none placeholder:text-dark-300/70 resize-none"
                      />
                    </div>
                  </div>

                  {/* Size breakdown toggle */}
                  {item.size_prices && item.size_prices.length > 1 && (
                    <div className="mt-2">
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={
                            !!(
                              item.size_quantities &&
                              item.size_quantities.length > 0
                            )
                          }
                          onChange={(e) => {
                            if (e.target.checked) {
                              const sq = item.size_prices!.map((sp) => ({
                                size: sp.size,
                                qty: 0,
                              }));
                              handleUpdateItem(itemId, {
                                size_quantities: sq,
                              });
                            } else {
                              handleUpdateItem(itemId, {
                                size_quantities: [],
                              });
                            }
                          }}
                          disabled={isUpdating}
                          className="w-3 h-3 rounded accent-accent"
                        />
                        <span className="text-[10px] text-dark-200">
                          Detaliaza pe marimi
                        </span>
                      </label>

                      {item.size_quantities &&
                        item.size_quantities.length > 0 && (
                          <div className="mt-1.5 grid grid-cols-4 gap-1">
                            {item.size_quantities.map((sq, idx) => (
                              <div
                                key={sq.size}
                                className="flex flex-col items-center"
                              >
                                <span className="text-[9px] text-dark-300 font-medium">
                                  {sq.size}
                                </span>
                                <input
                                  type="number"
                                  min={0}
                                  defaultValue={sq.qty || ""}
                                  key={`sq-${itemId}-${sq.size}-${sq.qty}`}
                                  placeholder="0"
                                  onBlur={(e) => {
                                    const val =
                                      parseInt(e.target.value, 10) || 0;
                                    if (val !== sq.qty) {
                                      const updated = [
                                        ...item.size_quantities!,
                                      ];
                                      updated[idx] = {
                                        ...updated[idx],
                                        qty: val,
                                      };
                                      handleUpdateItem(itemId, {
                                        size_quantities: updated,
                                      });
                                    }
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter")
                                      (
                                        e.target as HTMLInputElement
                                      ).blur();
                                  }}
                                  disabled={isUpdating}
                                  className="w-full text-[10px] text-dark-50 text-center bg-dark-400/40 rounded px-0.5 py-0.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                />
                              </div>
                            ))}
                          </div>
                        )}
                    </div>
                  )}

                  {/* Quantity controls + price */}
                  <div className="flex items-center justify-between mt-2">
                    <div className="flex items-center gap-1">
                      {!(
                        item.size_quantities &&
                        item.size_quantities.length > 0
                      ) ? (
                        <>
                          <button
                            onClick={() =>
                              handleUpdateQuantity(itemId, item.quantity - 1)
                            }
                            disabled={isUpdating || item.quantity <= 1}
                            className="w-6 h-6 rounded-md bg-dark-400/40 flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-400/60 transition-colors disabled:opacity-30"
                          >
                            <Minus size={10} />
                          </button>
                          <input
                            type="number"
                            min={1}
                            defaultValue={item.quantity}
                            key={`qty-${itemId}-${item.quantity}`}
                            onBlur={(e) => {
                              const val = parseInt(e.target.value, 10);
                              if (
                                !isNaN(val) &&
                                val >= 1 &&
                                val !== item.quantity
                              ) {
                                handleUpdateQuantity(itemId, val);
                              }
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                (e.target as HTMLInputElement).blur();
                              }
                            }}
                            disabled={isUpdating}
                            className="w-14 text-xs font-medium text-dark-50 text-center bg-dark-400/40 rounded-md px-1 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                          />
                          <button
                            onClick={() =>
                              handleUpdateQuantity(itemId, item.quantity + 1)
                            }
                            disabled={isUpdating}
                            className="w-6 h-6 rounded-md bg-dark-400/40 flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-400/60 transition-colors disabled:opacity-30"
                          >
                            <Plus size={10} />
                          </button>
                        </>
                      ) : (
                        <span className="text-xs font-medium text-dark-100 bg-dark-400/30 rounded-md px-2 py-1">
                          {item.quantity} buc
                        </span>
                      )}
                      <span className="text-[10px] text-dark-200 ml-1">
                        x{" "}
                        {(
                          item.sell_price * exchangeRate +
                          (item.printing_cost || 0)
                        ).toFixed(2)}{" "}
                        RON
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-dark-50">
                      {(
                        item.sell_price * exchangeRate * item.quantity +
                        (item.printing_cost || 0) * item.quantity +
                        (item.printing_setup || 0)
                      ).toFixed(2)}
                    </p>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>

        {/* Manual add product button + form */}
        <AnimatePresence>
          {showManualForm ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="p-3 rounded-xl bg-dark-500/30 border border-accent/20 space-y-2"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-medium text-accent">
                  Produs manual
                </span>
                <button
                  onClick={() => setShowManualForm(false)}
                  className="p-0.5 rounded text-dark-200 hover:text-dark-50"
                >
                  <X size={12} />
                </button>
              </div>

              <input
                type="text"
                placeholder="Nume produs *"
                value={manualForm.product_name}
                onChange={(e) =>
                  setManualForm((f) => ({
                    ...f,
                    product_name: e.target.value,
                  }))
                }
                className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
              />

              <div className="flex items-center gap-1.5">
                <label className="flex-1 flex items-center gap-1.5 cursor-pointer text-[11px] text-dark-200 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent hover:border-accent/30 transition-colors">
                  <Package
                    size={10}
                    className="text-dark-300 flex-shrink-0"
                  />
                  <span className="truncate">
                    {manualForm.product_image
                      ? "Imagine incarcata"
                      : "Incarca imagine produs"}
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
                        const res = await fetch(
                          `${API}/settings/upload/product-image`,
                          { method: "POST", body: fd }
                        );
                        if (!res.ok) throw new Error();
                        const data = await res.json();
                        setManualForm((f) => ({
                          ...f,
                          product_image: data.url,
                        }));
                      } catch {
                        /* error */
                      }
                    }}
                  />
                </label>
                {manualForm.product_image && (
                  <img
                    src={manualForm.product_image}
                    alt=""
                    className="w-8 h-8 rounded object-contain bg-white/5"
                  />
                )}
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <input
                  type="text"
                  placeholder="SKU / Cod"
                  value={manualForm.product_sku}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      product_sku: e.target.value,
                    }))
                  }
                  className="text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                />
                <input
                  type="text"
                  placeholder="Culoare"
                  value={manualForm.product_color}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      product_color: e.target.value,
                    }))
                  }
                  className="text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                />
              </div>

              <div className="grid grid-cols-3 gap-1.5">
                <div>
                  <label className="text-[9px] text-dark-300 block mb-0.5">
                    Cantitate
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={manualForm.quantity}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        quantity: parseInt(e.target.value) || 1,
                      }))
                    }
                    className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-dark-300 block mb-0.5">
                    Pret unit (EUR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={manualForm.unit_price || ""}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        unit_price: parseFloat(e.target.value) || 0,
                      }))
                    }
                    className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-dark-300 block mb-0.5">
                    Marja (%)
                  </label>
                  <input
                    type="number"
                    step="1"
                    min={0}
                    value={manualForm.margin_percent}
                    onChange={(e) =>
                      setManualForm((f) => ({
                        ...f,
                        margin_percent: parseFloat(e.target.value) || 0,
                      }))
                    }
                    className="w-full text-[11px] text-dark-50 bg-dark-400/30 rounded-md px-2 py-1.5 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <Printer size={10} className="text-dark-300 flex-shrink-0" />
                <input
                  type="text"
                  placeholder="Personalizare (ex: Tampografie)"
                  value={manualForm.printing_method}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      printing_method: e.target.value,
                    }))
                  }
                  className="flex-1 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none placeholder:text-dark-300"
                />
              </div>
              <div className="flex items-center gap-1.5 pl-4">
                <span className="text-[10px] text-dark-300 whitespace-nowrap">
                  RON/buc:
                </span>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  value={manualForm.printing_cost || ""}
                  onChange={(e) =>
                    setManualForm((f) => ({
                      ...f,
                      printing_cost: parseFloat(e.target.value) || 0,
                    }))
                  }
                  className="w-16 text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-transparent focus:border-accent/40 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
              </div>

              <textarea
                placeholder="Observatii (apare pe oferta)"
                rows={2}
                value={manualForm.customization_notes}
                onChange={(e) =>
                  setManualForm((f) => ({
                    ...f,
                    customization_notes: e.target.value,
                  }))
                }
                className="w-full text-[10px] text-dark-100 bg-dark-400/30 rounded-md px-1.5 py-1 border border-dark-400/60 focus:border-accent/40 focus:outline-none placeholder:text-dark-300/70 resize-none"
              />

              <button
                onClick={handleAddManualItem}
                disabled={isAddingManual || !manualForm.product_name.trim()}
                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isAddingManual ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Plus size={12} />
                )}
                Adauga produs
              </button>
            </motion.div>
          ) : (
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              onClick={() => setShowManualForm(true)}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-dark-400/40 text-[11px] text-dark-200 hover:text-accent hover:border-accent/30 transition-colors"
            >
              <Plus size={12} />
              Adauga produs manual
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[rgba(255,255,255,0.06)]">
        {/* Total */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-dark-100">Total</span>
          <span className="text-xl font-bold text-dark-50">
            {currentQuote.items
              .reduce((sum, it) => {
                const itemRon =
                  it.sell_price * exchangeRate * it.quantity +
                  (it.printing_cost || 0) * it.quantity +
                  (it.printing_setup || 0);
                return sum + itemRon;
              }, 0)
              .toFixed(2)}{" "}
            <span className="text-xs font-normal text-dark-200">RON</span>
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleGeneratePDF}
            disabled={isGeneratingPDF || currentQuote.items.length === 0}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium text-sm transition-all",
              "bg-success text-white hover:brightness-110 active:scale-[0.98] glow-success",
              "disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
            )}
          >
            {isGeneratingPDF ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Download size={16} />
            )}
            {isGeneratingPDF ? "Se genereaza..." : "Genereaza PDF"}
          </button>
          <button
            onClick={handleGenerateInternal}
            disabled={
              isGeneratingInternal || currentQuote.items.length === 0
            }
            title="Fisa interna comanda"
            className="flex items-center justify-center gap-1.5 px-3 py-3 rounded-xl text-xs font-medium bg-dark-400/30 text-dark-100 hover:text-dark-50 hover:bg-dark-400/50 border border-[rgba(255,255,255,0.04)] hover:border-[rgba(255,255,255,0.08)] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isGeneratingInternal ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <FileText size={14} />
            )}
          </button>
          <button className="flex items-center justify-center gap-1.5 px-3 py-3 rounded-xl text-xs font-medium bg-dark-400/30 text-dark-100 hover:text-dark-50 hover:bg-dark-400/50 border border-[rgba(255,255,255,0.04)] hover:border-[rgba(255,255,255,0.08)] transition-all">
            <Mail size={14} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// ── Client fields with autocomplete for saved-quote mode ─────────────
interface SavedQuoteClientFieldsProps {
  initialName: string;
  initialCompany: string;
  initialEmail: string;
  onCommit: (patch: Record<string, string>) => void;
}

function SavedQuoteClientFields({
  initialName,
  initialCompany,
  initialEmail,
  onCommit,
}: SavedQuoteClientFieldsProps) {
  const [name, setName] = useState(initialName);
  const [company, setCompany] = useState(initialCompany);
  const [email, setEmail] = useState(initialEmail);

  return (
    <div className="mt-2 p-2.5 rounded-xl bg-dark-400/20 text-xs space-y-1">
      <ClientAutocomplete
        field="client_name"
        value={name}
        onChange={setName}
        onPick={(s) => {
          setName(s.client_name);
          setCompany(s.client_company);
          setEmail(s.client_email);
          onCommit({
            client_name: s.client_name,
            client_company: s.client_company,
            client_email: s.client_email,
          });
        }}
        onBlur={() => {
          if (name !== initialName) onCommit({ client_name: name });
        }}
        placeholder="Nume client"
        className="w-full font-medium text-dark-50 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
      />
      <ClientAutocomplete
        field="client_company"
        value={company}
        onChange={setCompany}
        onPick={(s) => {
          setName(s.client_name);
          setCompany(s.client_company);
          setEmail(s.client_email);
          onCommit({
            client_name: s.client_name,
            client_company: s.client_company,
            client_email: s.client_email,
          });
        }}
        onBlur={() => {
          if (company !== initialCompany) onCommit({ client_company: company });
        }}
        placeholder="Companie"
        className="w-full text-dark-200 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
      />
      <ClientAutocomplete
        field="client_email"
        value={email}
        onChange={setEmail}
        onPick={(s) => {
          setName(s.client_name);
          setCompany(s.client_company);
          setEmail(s.client_email);
          onCommit({
            client_name: s.client_name,
            client_company: s.client_company,
            client_email: s.client_email,
          });
        }}
        onBlur={() => {
          if (email !== initialEmail) onCommit({ client_email: email });
        }}
        placeholder="Email client"
        className="w-full text-dark-200 bg-transparent border-b border-transparent hover:border-dark-400/40 focus:border-accent/40 focus:outline-none py-0.5 placeholder:text-dark-300"
      />
    </div>
  );
}
