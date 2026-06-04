"use client";

import { useEffect, useState } from "react";
import {
  Save,
  Loader2,
  Upload,
  Building2,
  Bot,
  Plus,
  Trash2,
  Star,
  Pencil,
  X,
  Check,
} from "lucide-react";
import {
  fetchSettings,
  updateSetting,
  fetchCompanies,
  createCompany,
  updateCompany,
  deleteCompany,
  setDefaultCompany,
} from "@/lib/api";
import type { Company } from "@/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const EMPTY_COMPANY: Omit<Company, "id" | "created_at"> = {
  name: "",
  cui: "",
  address: "",
  phone: "",
  email: "",
  website: "",
  bank: "",
  iban: "",
  logo_url: "",
  is_default: false,
};

export default function CompanyTab() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState(EMPTY_COMPANY);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // AI Instructions (kept separate from companies)
  const [aiInstructions, setAiInstructions] = useState("");
  const [savingAi, setSavingAi] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [companiesData, settings] = await Promise.all([
        fetchCompanies(),
        fetchSettings(),
      ]);
      setCompanies(companiesData);
      const ai = settings.find((s) => s.key === "ai_instructions")?.value ?? "";
      setAiInstructions(ai);
    } catch {
      // error loading
    }
    setLoading(false);
  };

  const handleStartEdit = (company: Company) => {
    setEditingId(company.id);
    setShowAddForm(false);
    setFormData({
      name: company.name,
      cui: company.cui,
      address: company.address,
      phone: company.phone,
      email: company.email,
      website: company.website,
      bank: company.bank,
      iban: company.iban,
      logo_url: company.logo_url,
      is_default: company.is_default,
    });
  };

  const handleStartAdd = () => {
    setEditingId(null);
    setShowAddForm(true);
    setFormData({ ...EMPTY_COMPANY });
  };

  const handleCancel = () => {
    setEditingId(null);
    setShowAddForm(false);
    setFormData({ ...EMPTY_COMPANY });
  };

  const handleSave = async () => {
    if (!formData.name.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        const updated = await updateCompany(editingId, formData);
        setCompanies((prev) =>
          prev.map((c) => (c.id === editingId ? updated : c))
        );
      } else {
        const created = await createCompany(formData);
        setCompanies((prev) => [...prev, created]);
      }
      handleCancel();
    } catch {
      // error
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await deleteCompany(id);
      setCompanies((prev) => prev.filter((c) => c.id !== id));
      if (editingId === id) handleCancel();
    } catch {
      // error
    }
    setDeleting(null);
  };

  const handleSetDefault = async (id: string) => {
    try {
      await setDefaultCompany(id);
      setCompanies((prev) =>
        prev.map((c) => ({ ...c, is_default: c.id === id }))
      );
    } catch {
      // error
    }
  };

  const handleLogoUpload = async (file: File, companyId?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API}/settings/upload/logo`, {
        method: "POST",
        body: fd,
      });
      if (res.ok) {
        const data = await res.json();
        const url = data.url ?? "";
        // Always update formData so Save doesn't overwrite with old value
        setFormData((prev) => ({ ...prev, logo_url: url }));
        if (companyId) {
          const updated = await updateCompany(companyId, { logo_url: url });
          setCompanies((prev) =>
            prev.map((c) => (c.id === companyId ? updated : c))
          );
        }
      }
    } catch {
      // upload failed
    }
  };

  const handleSaveAi = async () => {
    setSavingAi(true);
    await updateSetting("ai_instructions", aiInstructions);
    setSavingAi(false);
  };

  const inputClass =
    "w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30 placeholder:text-dark-300";

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-accent" size={24} />
      </div>
    );
  }

  const renderCompanyForm = () => (
    <div className="p-5 rounded-2xl border border-accent/20 bg-dark-500/30 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-dark-50">
          {editingId ? "Editează companie" : "Adaugă companie nouă"}
        </h4>
        <button
          onClick={handleCancel}
          className="p-1.5 rounded-lg text-dark-300 hover:text-dark-50 hover:bg-dark-400/30 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {/* Logo */}
      <div className="flex items-center gap-4">
        <div className="w-16 h-16 rounded-xl bg-dark-400/30 border border-[rgba(255,255,255,0.06)] flex items-center justify-center overflow-hidden flex-shrink-0">
          {formData.logo_url ? (
            <img
              src={formData.logo_url}
              alt="Logo"
              className="w-full h-full object-contain p-1.5"
            />
          ) : (
            <Building2 size={24} className="text-dark-300" />
          )}
        </div>
        <label className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium bg-dark-400/40 text-dark-100 hover:bg-dark-400/60 cursor-pointer transition-all border border-[rgba(255,255,255,0.06)]">
          <Upload size={12} />
          Logo
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleLogoUpload(file, editingId ?? undefined);
            }}
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            Nume firmă *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) =>
              setFormData((p) => ({ ...p, name: e.target.value }))
            }
            placeholder="Demo Company SRL"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            CUI / CIF
          </label>
          <input
            type="text"
            value={formData.cui}
            onChange={(e) =>
              setFormData((p) => ({ ...p, cui: e.target.value }))
            }
            placeholder="RO12345678"
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
          Adresă
        </label>
        <input
          type="text"
          value={formData.address}
          onChange={(e) =>
            setFormData((p) => ({ ...p, address: e.target.value }))
          }
          placeholder="Str. Exemplu nr. 1, București"
          className={inputClass}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            Telefon
          </label>
          <input
            type="text"
            value={formData.phone}
            onChange={(e) =>
              setFormData((p) => ({ ...p, phone: e.target.value }))
            }
            placeholder="+40 700 000 000"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            Email
          </label>
          <input
            type="email"
            value={formData.email}
            onChange={(e) =>
              setFormData((p) => ({ ...p, email: e.target.value }))
            }
            placeholder="office@company.ro"
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
          Website
        </label>
        <input
          type="text"
          value={formData.website}
          onChange={(e) =>
            setFormData((p) => ({ ...p, website: e.target.value }))
          }
          placeholder="https://www.company.ro"
          className={inputClass}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            Bancă
          </label>
          <input
            type="text"
            value={formData.bank}
            onChange={(e) =>
              setFormData((p) => ({ ...p, bank: e.target.value }))
            }
            placeholder="Banca Transilvania"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1">
            IBAN
          </label>
          <input
            type="text"
            value={formData.iban}
            onChange={(e) =>
              setFormData((p) => ({ ...p, iban: e.target.value }))
            }
            placeholder="RO49AAAA1B31007593840000"
            className={inputClass}
          />
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving || !formData.name.trim()}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
        >
          {saving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Check size={14} />
          )}
          {editingId ? "Salvează" : "Adaugă"}
        </button>
        <button
          onClick={handleCancel}
          className="px-4 py-2.5 rounded-xl text-sm font-medium text-dark-200 hover:text-dark-50 transition-colors"
        >
          Anulează
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-8 max-w-2xl">
      {/* Companies list */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-dark-50">
              Companii
            </h3>
            <p className="text-xs text-dark-200 mt-0.5">
              Gestionează companiile din care poți oferta. Compania implicită
              este selectată automat la oferte noi.
            </p>
          </div>
          {!showAddForm && !editingId && (
            <button
              onClick={handleStartAdd}
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover transition-all"
            >
              <Plus size={14} />
              Adaugă
            </button>
          )}
        </div>

        {/* Company cards */}
        <div className="space-y-3">
          {companies.map((company) =>
            editingId === company.id ? (
              <div key={company.id}>{renderCompanyForm()}</div>
            ) : (
              <div
                key={company.id}
                className={`p-4 rounded-2xl border transition-all ${
                  company.is_default
                    ? "border-accent/30 bg-accent/5"
                    : "border-[rgba(255,255,255,0.06)] bg-dark-500/20"
                }`}
              >
                <div className="flex items-start gap-4">
                  {/* Logo */}
                  <div className="w-12 h-12 rounded-xl bg-dark-400/30 border border-[rgba(255,255,255,0.06)] flex items-center justify-center overflow-hidden flex-shrink-0">
                    {company.logo_url ? (
                      <img
                        src={company.logo_url}
                        alt={company.name}
                        className="w-full h-full object-contain p-1"
                      />
                    ) : (
                      <Building2 size={20} className="text-dark-300" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-dark-50 text-sm">
                        {company.name}
                      </p>
                      {company.is_default && (
                        <span className="text-[10px] font-medium bg-accent/20 text-accent px-1.5 py-0.5 rounded-full flex items-center gap-1">
                          <Star size={8} />
                          Implicită
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-xs text-dark-200">
                      {company.cui && <span>CUI: {company.cui}</span>}
                      {company.email && <span>{company.email}</span>}
                      {company.phone && <span>{company.phone}</span>}
                    </div>
                    {company.address && (
                      <p className="text-xs text-dark-300 mt-0.5">
                        {company.address}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {!company.is_default && (
                      <button
                        onClick={() => handleSetDefault(company.id)}
                        className="p-2 rounded-lg text-dark-300 hover:text-accent hover:bg-accent/10 transition-all"
                        title="Setează ca implicită"
                      >
                        <Star size={14} />
                      </button>
                    )}
                    <button
                      onClick={() => handleStartEdit(company)}
                      className="p-2 rounded-lg text-dark-300 hover:text-dark-50 hover:bg-dark-400/30 transition-all"
                      title="Editează"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(company.id)}
                      disabled={deleting === company.id}
                      className="p-2 rounded-lg text-dark-300 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-40"
                      title="Șterge"
                    >
                      {deleting === company.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Trash2 size={14} />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )
          )}

          {companies.length === 0 && !showAddForm && (
            <div className="text-center py-8 text-dark-300 text-sm">
              Nicio companie adăugată. Adaugă prima companie pentru a putea
              genera oferte.
            </div>
          )}
        </div>

        {/* Add form */}
        {showAddForm && renderCompanyForm()}
      </section>

      {/* AI Instructions */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-dark-50 flex items-center gap-2">
            <Bot size={18} className="text-accent" />
            Instrucțiuni AI
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Instrucțiuni personalizate pentru agentul AI. Acesta le va urma la
            fiecare conversație.
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 space-y-4">
          <textarea
            value={aiInstructions}
            onChange={(e) => setAiInstructions(e.target.value)}
            rows={8}
            placeholder={`Exemplu:\n- Răspunde întotdeauna în limba română\n- Recomandă produse premium clienților enterprise\n- Oferă discount de 5% la comenzi peste 500 EUR\n- Menționează timpul de livrare de 7-10 zile lucrătoare`}
            className={`${inputClass} resize-y min-h-[120px] font-mono text-[13px] leading-relaxed`}
          />
          <div className="flex items-center justify-between">
            <p className="text-[11px] text-dark-300">
              {aiInstructions.length} caractere
            </p>
            <button
              onClick={handleSaveAi}
              disabled={savingAi}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
            >
              {savingAi ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Save size={14} />
              )}
              Salvează instrucțiuni
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
