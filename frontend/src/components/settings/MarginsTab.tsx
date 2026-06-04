"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Save, Loader2, Plus, Trash2, Calculator } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  fetchSettings,
  updateSetting,
  getCategoryMargins,
  updateCategoryMargins,
  getCategories,
} from "@/lib/api";
import type { AppSetting, CategoryCount } from "@/types";

export default function MarginsTab() {
  const [globalMargin, setGlobalMargin] = useState(30);
  const [currency, setCurrency] = useState("EUR");
  const [exchangeRate, setExchangeRate] = useState(4.97);
  const [categoryMargins, setCategoryMargins] = useState<
    Record<string, number>
  >({});
  const [categories, setCategories] = useState<CategoryCount[]>([]);
  const [saving, setSaving] = useState(false);
  const [previewPrice, setPreviewPrice] = useState(50);

  useEffect(() => {
    fetchSettings().then((settings) => {
      const margin = settings.find((s) => s.key === "margin_percent");
      const curr = settings.find((s) => s.key === "currency");
      const rate = settings.find((s) => s.key === "exchange_rate_eur_ron");
      if (margin) setGlobalMargin(Number(margin.value));
      if (curr) setCurrency(curr.value);
      if (rate) setExchangeRate(Number(rate.value));
    });
    getCategoryMargins().then(setCategoryMargins);
    getCategories().then(setCategories).catch(() => {});
  }, []);

  const handleSaveGlobal = async () => {
    setSaving(true);
    await updateSetting("margin_percent", String(globalMargin));
    await updateSetting("currency", currency);
    await updateSetting("exchange_rate_eur_ron", String(exchangeRate));
    setSaving(false);
  };

  const handleSaveCategoryMargins = async () => {
    setSaving(true);
    await updateCategoryMargins(categoryMargins);
    setSaving(false);
  };

  const addCategoryMargin = (category: string) => {
    if (!category || category in categoryMargins) return;
    setCategoryMargins({ ...categoryMargins, [category]: globalMargin });
  };

  const removeCategoryMargin = (category: string) => {
    const next = { ...categoryMargins };
    delete next[category];
    setCategoryMargins(next);
  };

  const sellPrice = (basePrice: number, margin: number) =>
    (basePrice * (1 + margin / 100)).toFixed(2);

  return (
    <div className="space-y-8 max-w-2xl">
      {/* Global Margin */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-dark-50">
            Marja globală
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Aplicată tuturor produselor fără marjă specifică pe categorie
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-dark-100">Marja implicită</label>
              <span className="text-2xl font-bold text-dark-50">
                {globalMargin}
                <span className="text-sm font-normal text-dark-200">%</span>
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={globalMargin}
              onChange={(e) => setGlobalMargin(Number(e.target.value))}
              className="w-full accent-accent"
            />
            <div className="flex justify-between text-[10px] text-dark-300 mt-1">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Moneda implicită
              </label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
              >
                <option value="EUR">EUR (Euro)</option>
                <option value="RON">RON (Leu)</option>
                <option value="USD">USD (Dollar)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Curs EUR → RON
              </label>
              <input
                type="number"
                step="0.01"
                value={exchangeRate}
                onChange={(e) => setExchangeRate(Number(e.target.value))}
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
              />
            </div>
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Simulare preț
              </label>
              <input
                type="number"
                value={previewPrice}
                onChange={(e) => setPreviewPrice(Number(e.target.value))}
                className="w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
              />
            </div>
          </div>

          {/* Preview */}
          <div className="flex items-center gap-3 p-3 rounded-xl bg-accent/5 border border-accent/10">
            <Calculator size={16} className="text-accent" />
            <div className="text-sm text-dark-100">
              <p>
                Preț achiziție{" "}
                <strong className="text-dark-50">
                  {previewPrice} EUR
                </strong>{" "}
                cu marjă {globalMargin}% →{" "}
                <strong className="text-accent text-lg">
                  {sellPrice(previewPrice, globalMargin)} EUR
                </strong>
              </p>
              <p className="mt-1">
                În RON:{" "}
                <strong className="text-accent text-lg">
                  {(Number(sellPrice(previewPrice, globalMargin)) * exchangeRate).toFixed(2)} RON
                </strong>
              </p>
            </div>
          </div>

          <button
            onClick={handleSaveGlobal}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Salvează
          </button>
        </div>
      </section>

      {/* Category Margins */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-dark-50">
              Marje pe categorii
            </h3>
            <p className="text-xs text-dark-200 mt-0.5">
              Suprascrie marja globală pentru categorii specifice
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] overflow-hidden">
          {Object.keys(categoryMargins).length === 0 ? (
            <div className="p-6 text-center text-dark-300 text-sm">
              Nicio marjă pe categorie configurată. Se va folosi marja globală.
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="bg-dark-500/30">
                  <th className="text-left text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-2.5">
                    Categorie
                  </th>
                  <th className="text-center text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-2.5">
                    Marjă %
                  </th>
                  <th className="text-center text-[11px] font-semibold text-dark-200 uppercase tracking-wider px-4 py-2.5">
                    Preț final la {previewPrice}
                  </th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(255,255,255,0.04)]">
                {Object.entries(categoryMargins).map(([cat, margin]) => (
                  <motion.tr
                    key={cat}
                    layout
                    className="hover:bg-dark-400/10"
                  >
                    <td className="px-4 py-2.5 text-sm text-dark-50">
                      {cat}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={margin}
                        onChange={(e) =>
                          setCategoryMargins({
                            ...categoryMargins,
                            [cat]: Number(e.target.value),
                          })
                        }
                        className="w-20 bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-lg px-2 py-1 text-sm text-dark-50 text-center outline-none focus:border-accent/30"
                      />
                    </td>
                    <td className="px-4 py-2.5 text-center text-sm text-accent font-medium">
                      {sellPrice(previewPrice, margin)} {currency}
                    </td>
                    <td className="pr-3">
                      <button
                        onClick={() => removeCategoryMargin(cat)}
                        className="p-1.5 rounded-lg text-dark-300 hover:text-red-400 hover:bg-red-500/10 transition-all"
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Add category */}
        <div className="flex gap-2">
          <select
            id="add-category"
            className="flex-1 bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30"
            defaultValue=""
            onChange={(e) => {
              addCategoryMargin(e.target.value);
              e.target.value = "";
            }}
          >
            <option value="" disabled>
              Adaugă categorie...
            </option>
            {categories
              .filter((c) => !(c.name in categoryMargins))
              .map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.count} produse)
                </option>
              ))}
          </select>
          <button
            onClick={handleSaveCategoryMargins}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Salvează marje
          </button>
        </div>
      </section>
    </div>
  );
}
