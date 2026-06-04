"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  RefreshCw,
  Trash2,
  Edit2,
  Power,
  PowerOff,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Globe,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import {
  fetchIntegrations,
  createIntegration,
  updateIntegration,
  deleteIntegration,
  triggerSync,
  subscribeSyncProgress,
} from "@/lib/api";
import type { Integration, IntegrationCreate, SyncProgress } from "@/types";

const INTEGRATION_TYPES = [
  { value: "anda_present", label: "ANDA Present", description: "XML feed ANDA" },
  { value: "midocean", label: "Midocean", description: "Midocean API" },
  { value: "makito", label: "Makito", description: "REST API data.makito.es" },
  { value: "easygifts", label: "EasyGifts", description: "JSON feed EasyGifts" },
  { value: "malfini", label: "Malfini", description: "API Malfini" },
  { value: "macma", label: "Macma", description: "JSON feed Macma" },
  { value: "roly", label: "Roly", description: "XLSX Roly" },
  { value: "stamina", label: "Stamina", description: "XLSX Stamina" },
  { value: "utt", label: "UTT (TShirt Europe)", description: "API TShirt Europe" },
  { value: "generic_xml", label: "XML Generic", description: "Feed XML configurabil" },
  { value: "woocommerce", label: "WooCommerce", description: "REST API (viitor)" },
];

const SYNC_FREQUENCIES = [
  { value: "manual", label: "Manual" },
  { value: "daily", label: "Zilnic" },
  { value: "weekly", label: "Săptămânal" },
];

export default function IntegrationsTab() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState<Record<string, SyncProgress>>({});

  const loadIntegrations = useCallback(async () => {
    try {
      const data = await fetchIntegrations();
      setIntegrations(data);
    } catch {
      // handle error
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const handleToggle = async (integration: Integration) => {
    await updateIntegration(integration.id, {
      is_active: !integration.is_active,
    });
    loadIntegrations();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Ești sigur că vrei să ștergi această integrare?")) return;
    await deleteIntegration(id);
    loadIntegrations();
  };

  const handleSync = async (integration: Integration) => {
    try {
      await triggerSync(integration.id);
      // Subscribe to SSE progress
      const unsub = subscribeSyncProgress(integration.id, (progress) => {
        setSyncProgress((prev) => ({ ...prev, [integration.id]: progress }));
        if (progress.stage === "done" || progress.stage === "error") {
          setTimeout(() => {
            setSyncProgress((prev) => {
              const next = { ...prev };
              delete next[integration.id];
              return next;
            });
            loadIntegrations();
          }, 3000);
        }
      });
      // Clean up after 5 minutes max
      setTimeout(unsub, 300000);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Eroare la sincronizare");
    }
  };

  const handleSave = async (data: IntegrationCreate) => {
    if (editingId) {
      await updateIntegration(editingId, data as Partial<Integration>);
    } else {
      await createIntegration(data);
    }
    setShowModal(false);
    setEditingId(null);
    loadIntegrations();
  };

  const handleEdit = (integration: Integration) => {
    setEditingId(integration.id);
    setShowModal(true);
  };

  const editingIntegration = editingId
    ? integrations.find((i) => i.id === editingId)
    : undefined;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-dark-200" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-dark-50">
            Integrări API
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Configurează sursele de produse și sincronizarea
          </p>
        </div>
        <button
          onClick={() => {
            setEditingId(null);
            setShowModal(true);
          }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover transition-all active:scale-95"
        >
          <Plus size={16} />
          Adaugă Integrare
        </button>
      </div>

      {/* Table */}
      <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-dark-500/30">
              <th className="text-left text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Integrare
              </th>
              <th className="text-left text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Tip
              </th>
              <th className="text-center text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Produse
              </th>
              <th className="text-left text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Ultima sync
              </th>
              <th className="text-center text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Status
              </th>
              <th className="text-right text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-3">
                Acțiuni
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[rgba(255,255,255,0.04)]">
            {integrations.map((integration) => {
              const progress = syncProgress[integration.id];
              const isSyncing =
                progress || integration.last_sync_status === "in_progress";

              return (
                <tr
                  key={integration.id}
                  className="hover:bg-dark-400/10 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-8 h-8 rounded-lg flex items-center justify-center",
                          integration.is_active
                            ? "bg-accent/10 text-accent"
                            : "bg-dark-400/30 text-dark-300"
                        )}
                      >
                        <Globe size={16} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-dark-50">
                          {integration.display_name || integration.name}
                        </p>
                        <p className="text-[10px] text-dark-300 font-mono">
                          {integration.name}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-dark-100">
                      {INTEGRATION_TYPES.find(
                        (t) => t.value === integration.integration_type
                      )?.label ?? integration.integration_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-sm font-semibold text-dark-50">
                      {integration.products_count.toLocaleString("ro-RO")}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {integration.last_sync_at ? (
                      <div className="flex items-center gap-1.5 text-xs text-dark-200">
                        <Clock size={12} />
                        {new Date(integration.last_sync_at).toLocaleString(
                          "ro-RO",
                          {
                            day: "2-digit",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          }
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-dark-300">Niciodată</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <StatusBadge
                      status={
                        progress?.stage === "error"
                          ? "error"
                          : isSyncing
                          ? "in_progress"
                          : integration.last_sync_status
                      }
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleSync(integration)}
                        disabled={!integration.is_active || !!isSyncing}
                        className="p-2 rounded-lg text-dark-200 hover:text-accent hover:bg-accent/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                        title="Sincronizează"
                      >
                        <RefreshCw
                          size={14}
                          className={isSyncing ? "animate-spin" : ""}
                        />
                      </button>
                      <button
                        onClick={() => handleToggle(integration)}
                        className={cn(
                          "p-2 rounded-lg transition-all",
                          integration.is_active
                            ? "text-green-400 hover:bg-green-500/10"
                            : "text-dark-300 hover:text-dark-100 hover:bg-dark-400/30"
                        )}
                        title={
                          integration.is_active ? "Dezactivează" : "Activează"
                        }
                      >
                        {integration.is_active ? (
                          <Power size={14} />
                        ) : (
                          <PowerOff size={14} />
                        )}
                      </button>
                      <button
                        onClick={() => handleEdit(integration)}
                        className="p-2 rounded-lg text-dark-200 hover:text-dark-50 hover:bg-dark-400/30 transition-all"
                        title="Editează"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(integration.id)}
                        className="p-2 rounded-lg text-dark-200 hover:text-red-400 hover:bg-red-500/10 transition-all"
                        title="Șterge"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Sync progress bars */}
      <AnimatePresence>
        {Object.entries(syncProgress).map(([id, progress]) => (
          <motion.div
            key={id}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 p-4 space-y-2"
          >
            <div className="flex items-center justify-between text-xs">
              <span className="text-dark-100 font-medium">
                {integrations.find((i) => i.id === id)?.display_name}
              </span>
              <span className="text-dark-200">{progress.percent}%</span>
            </div>
            <div className="h-2 bg-dark-400/30 rounded-full overflow-hidden">
              <motion.div
                className={cn(
                  "h-full rounded-full transition-all",
                  progress.stage === "error"
                    ? "bg-red-500"
                    : progress.stage === "done"
                    ? "bg-success"
                    : "bg-accent"
                )}
                initial={{ width: 0 }}
                animate={{ width: `${progress.percent}%` }}
              />
            </div>
            <p className="text-[11px] text-dark-200">{progress.message}</p>
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Integration Modal */}
      <AnimatePresence>
        {showModal && (
          <IntegrationModal
            integration={editingIntegration}
            onSave={handleSave}
            onClose={() => {
              setShowModal(false);
              setEditingId(null);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; icon: React.ElementType; color: string }> = {
    success: { label: "OK", icon: CheckCircle2, color: "text-green-400 bg-green-500/10" },
    error: { label: "Eroare", icon: XCircle, color: "text-red-400 bg-red-500/10" },
    in_progress: { label: "Sync...", icon: Loader2, color: "text-accent bg-accent/10" },
  };

  const cfg = config[status] || {
    label: status || "-",
    icon: Clock,
    color: "text-dark-300 bg-dark-400/20",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium",
        cfg.color
      )}
    >
      <cfg.icon size={10} className={status === "in_progress" ? "animate-spin" : ""} />
      {cfg.label}
    </span>
  );
}

/* ---------- helpers for extra_config field editing ---------- */
function useExtraField(
  form: IntegrationCreate,
  update: (field: string, value: unknown) => void,
) {
  const ec = (form.extra_config ?? {}) as Record<string, string>;
  const get = (key: string) => ec[key] ?? "";
  const set = (key: string, value: string) =>
    update("extra_config", { ...ec, [key]: value });
  return { get, set };
}

const inputCls =
  "w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30";

function CredentialFields({
  form,
  update,
}: {
  form: IntegrationCreate;
  update: (field: string, value: unknown) => void;
}) {
  const { get, set } = useExtraField(form, update);
  const t = form.integration_type;

  // --- Makito: email + password (auto-login) ---
  if (t === "makito") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">Email</label>
            <input type="email" value={get("email")} onChange={(e) => set("email", e.target.value)} placeholder="email@example.com" className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">Parolă</label>
            <input type="password" value={get("password")} onChange={(e) => set("password", e.target.value)} placeholder="••••••••" className={inputCls} />
          </div>
        </div>
        <p className="text-[10px] text-dark-300 -mt-1">Autentificare automată la fiecare sincronizare</p>
      </>
    );
  }

  // --- Malfini: username + password ---
  if (t === "malfini") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">Username</label>
            <input value={get("username")} onChange={(e) => set("username", e.target.value)} placeholder="user" className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">Parolă</label>
            <input type="password" value={get("password")} onChange={(e) => set("password", e.target.value)} placeholder="••••••••" className={inputCls} />
          </div>
        </div>
        <p className="text-[10px] text-dark-300 -mt-1">Login automat la fiecare sincronizare prin Bearer token</p>
      </>
    );
  }

  // --- ANDA: api_key + 4 URL-uri feed ---
  if (t === "anda_present") {
    return (
      <>
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">API Key</label>
          <input type="password" value={form.api_key ?? ""} onChange={(e) => update("api_key", e.target.value)} placeholder="••••••••" className={inputCls} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">URL Produse</label>
            <input value={get("products_url")} onChange={(e) => set("products_url", e.target.value)} placeholder="https://..." className={cn(inputCls, "font-mono text-xs")} />
          </div>
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">URL Prețuri</label>
            <input value={get("prices_url")} onChange={(e) => set("prices_url", e.target.value)} placeholder="https://..." className={cn(inputCls, "font-mono text-xs")} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">URL Stocuri</label>
            <input value={get("inventory_url")} onChange={(e) => set("inventory_url", e.target.value)} placeholder="https://..." className={cn(inputCls, "font-mono text-xs")} />
          </div>
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">URL Personalizări</label>
            <input value={get("labeling_url")} onChange={(e) => set("labeling_url", e.target.value)} placeholder="https://..." className={cn(inputCls, "font-mono text-xs")} />
          </div>
        </div>
      </>
    );
  }

  // --- Midocean / UTT: just api_key ---
  if (t === "midocean" || t === "utt") {
    return (
      <div>
        <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">API Key</label>
        <input type="password" value={form.api_key ?? ""} onChange={(e) => update("api_key", e.target.value)} placeholder="••••••••" className={inputCls} />
      </div>
    );
  }

  // --- EasyGifts / Macma: local JSON paths ---
  if (t === "easygifts" || t === "macma") {
    return (
      <div>
        <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
          Cale fișiere JSON (pe server, separate prin virgulă)
        </label>
        <input
          value={(() => {
            const paths = (form.extra_config as Record<string, unknown>)?.json_paths;
            return Array.isArray(paths) ? paths.join(", ") : "";
          })()}
          onChange={(e) => {
            const paths = e.target.value.split(",").map((p) => p.trim()).filter(Boolean);
            update("extra_config", { ...((form.extra_config as Record<string, string>) ?? {}), json_paths: paths });
          }}
          placeholder="/path/to/products.json"
          className={cn(inputCls, "font-mono text-xs")}
        />
      </div>
    );
  }

  // --- Roly / Stamina: XLSX paths ---
  if (t === "roly" || t === "stamina") {
    return (
      <div>
        <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
          Cale fișiere XLSX (pe server, separate prin virgulă)
        </label>
        <input
          value={(() => {
            const paths = (form.extra_config as Record<string, unknown>)?.xlsx_paths;
            return Array.isArray(paths) ? paths.join(", ") : "";
          })()}
          onChange={(e) => {
            const paths = e.target.value.split(",").map((p) => p.trim()).filter(Boolean);
            update("extra_config", { ...((form.extra_config as Record<string, string>) ?? {}), xlsx_paths: paths });
          }}
          placeholder="/path/to/catalog.xlsx"
          className={cn(inputCls, "font-mono text-xs")}
        />
      </div>
    );
  }

  // --- Default: api_key ---
  return (
    <div>
      <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">API Key</label>
      <input type="password" value={form.api_key ?? ""} onChange={(e) => update("api_key", e.target.value)} placeholder="••••••••" className={inputCls} />
    </div>
  );
}

function IntegrationModal({
  integration,
  onSave,
  onClose,
}: {
  integration?: Integration;
  onSave: (data: IntegrationCreate) => Promise<void>;
  onClose: () => void;
}) {
  const [form, setForm] = useState<IntegrationCreate>({
    name: integration?.name ?? "",
    display_name: integration?.display_name ?? "",
    integration_type: integration?.integration_type ?? "anda_present",
    api_url: integration?.api_url ?? "",
    api_key: integration?.api_key ?? "",
    api_user: integration?.api_user ?? "",
    api_password: integration?.api_password ?? "",
    extra_config: integration?.extra_config ?? {},
    default_margin: integration?.default_margin ?? 30,
    sync_frequency: integration?.sync_frequency ?? "manual",
    is_active: integration?.is_active ?? false,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(form);
    } catch {
      // handle
    }
    setSaving(false);
  };

  const update = (field: string, value: unknown) =>
    setForm((f) => ({ ...f, [field]: value }));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <motion.form
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="relative w-full max-w-lg glass-panel rounded-3xl p-6 space-y-4 shadow-2xl shadow-black/40"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-dark-50">
            {integration ? "Editează Integrare" : "Integrare Nouă"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-dark-400/50 flex items-center justify-center text-dark-100 hover:text-white hover:bg-dark-300 transition-all"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3">
          {/* Type */}
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
              Tip integrare
            </label>
            <select
              value={form.integration_type}
              onChange={(e) => update("integration_type", e.target.value)}
              className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
            >
              {INTEGRATION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label} — {t.description}
                </option>
              ))}
            </select>
          </div>

          {/* Name + Display Name */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Identificator
              </label>
              <input
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                placeholder="ex: anda_main"
                disabled={!!integration}
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30 disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Nume afișat
              </label>
              <input
                value={form.display_name}
                onChange={(e) => update("display_name", e.target.value)}
                placeholder="ANDA Present"
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
              />
            </div>
          </div>

          {/* URL Endpoint — always shown */}
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
              URL Endpoint
            </label>
            <input
              value={form.api_url}
              onChange={(e) => update("api_url", e.target.value)}
              placeholder="https://..."
              className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30 font-mono text-xs"
            />
          </div>

          {/* Dynamic credential fields per integration type */}
          <CredentialFields form={form} update={update} />

          {/* Sync frequency + Margin */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Frecvență Sync
              </label>
              <select
                value={form.sync_frequency}
                onChange={(e) => update("sync_frequency", e.target.value)}
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
              >
                {SYNC_FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Marja implicită: {form.default_margin}%
              </label>
              <input
                type="range"
                min={-50}
                max={100}
                step={1}
                value={form.default_margin}
                onChange={(e) => update("default_margin", Number(e.target.value))}
                className="w-full accent-accent"
              />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl text-sm font-medium text-dark-100 hover:text-dark-50 hover:bg-dark-400/30 border border-[rgba(255,255,255,0.06)] transition-all"
          >
            Anulează
          </button>
          <button
            type="submit"
            disabled={saving || !form.name || !form.display_name}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {integration ? "Salvează" : "Creează"}
          </button>
        </div>
      </motion.form>
    </motion.div>
  );
}
