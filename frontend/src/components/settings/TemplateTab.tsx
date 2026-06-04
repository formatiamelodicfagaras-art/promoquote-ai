"use client";

import { useEffect, useState } from "react";
import { Save, Loader2, Palette, Type, Layout } from "lucide-react";
import { fetchSettings, batchUpdateSettings } from "@/lib/api";

export default function TemplateTab() {
  const [primaryColor, setPrimaryColor] = useState("#6366f1");
  const [accentColor, setAccentColor] = useState("#10b981");
  const [fontFamily, setFontFamily] = useState("Inter");
  const [headerLayout, setHeaderLayout] = useState("logo-left");
  const [showPriceBreakdown, setShowPriceBreakdown] = useState(true);
  const [footerText, setFooterText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings().then((settings) => {
      const get = (key: string, fallback: string) =>
        settings.find((s) => s.key === key)?.value ?? fallback;
      setPrimaryColor(get("template_primary_color", "#6366f1"));
      setAccentColor(get("template_accent_color", "#10b981"));
      setFontFamily(get("template_font", "Inter"));
      setHeaderLayout(get("template_header_layout", "logo-left"));
      setShowPriceBreakdown(get("template_show_breakdown", "true") === "true");
      setFooterText(get("template_footer_text", ""));
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    await batchUpdateSettings({
      template_primary_color: primaryColor,
      template_accent_color: accentColor,
      template_font: fontFamily,
      template_header_layout: headerLayout,
      template_show_breakdown: String(showPriceBreakdown),
      template_footer_text: footerText,
    });
    setSaving(false);
  };

  const inputClass =
    "w-full bg-dark-400/30 border border-[rgba(255,255,255,0.06)] rounded-xl px-3 py-2.5 text-sm text-dark-50 outline-none focus:border-accent/30";

  return (
    <div className="space-y-8 max-w-2xl">
      {/* Colors */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-dark-50 flex items-center gap-2">
            <Palette size={18} className="text-accent" />
            Culori template
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Culorile folosite în ofertele PDF generate
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Culoare principală
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="w-10 h-10 rounded-lg border border-[rgba(255,255,255,0.06)] cursor-pointer bg-transparent"
                />
                <input
                  type="text"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className={`${inputClass} flex-1 font-mono text-xs`}
                />
              </div>
            </div>
            <div>
              <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
                Culoare accent
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={accentColor}
                  onChange={(e) => setAccentColor(e.target.value)}
                  className="w-10 h-10 rounded-lg border border-[rgba(255,255,255,0.06)] cursor-pointer bg-transparent"
                />
                <input
                  type="text"
                  value={accentColor}
                  onChange={(e) => setAccentColor(e.target.value)}
                  className={`${inputClass} flex-1 font-mono text-xs`}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Typography */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-dark-50 flex items-center gap-2">
            <Type size={18} className="text-accent" />
            Tipografie
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Fontul folosit în documentele PDF
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20">
          <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
            Font family
          </label>
          <select
            value={fontFamily}
            onChange={(e) => setFontFamily(e.target.value)}
            className={inputClass}
          >
            <option value="Inter">Inter</option>
            <option value="Roboto">Roboto</option>
            <option value="Open Sans">Open Sans</option>
            <option value="Lato">Lato</option>
            <option value="Montserrat">Montserrat</option>
            <option value="Poppins">Poppins</option>
          </select>
        </div>
      </section>

      {/* Layout */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-dark-50 flex items-center gap-2">
            <Layout size={18} className="text-accent" />
            Layout
          </h3>
          <p className="text-xs text-dark-200 mt-0.5">
            Structura vizuală a ofertei PDF
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-dark-500/20 space-y-4">
          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
              Poziție header
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { value: "logo-left", label: "Logo stânga" },
                { value: "logo-center", label: "Logo centru" },
                { value: "logo-right", label: "Logo dreapta" },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setHeaderLayout(opt.value)}
                  className={`px-3 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                    headerLayout === opt.value
                      ? "bg-accent/10 border-accent/30 text-accent"
                      : "bg-dark-400/20 border-[rgba(255,255,255,0.06)] text-dark-200 hover:text-dark-100"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-100">
                Afișează detalii preț
              </p>
              <p className="text-[11px] text-dark-300">
                Preț unitar, marjă și subtotal per produs
              </p>
            </div>
            <button
              onClick={() => setShowPriceBreakdown(!showPriceBreakdown)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                showPriceBreakdown ? "bg-accent" : "bg-dark-400/50"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  showPriceBreakdown ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          <div>
            <label className="block text-[11px] text-dark-200 uppercase tracking-wider mb-1.5">
              Text footer ofertă
            </label>
            <textarea
              value={footerText}
              onChange={(e) => setFooterText(e.target.value)}
              rows={3}
              placeholder="Ex: Oferta este valabilă 30 de zile de la data emiterii."
              className={`${inputClass} resize-y`}
            />
          </div>
        </div>
      </section>

      {/* PDF Preview */}
      <section className="space-y-4">
        <h3 className="text-base font-semibold text-dark-50">
          Preview template
        </h3>

        <div
          className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-white overflow-hidden"
          style={{ fontFamily }}
        >
          {/* Mini PDF preview */}
          <div className="p-6 space-y-4" style={{ fontSize: "11px" }}>
            {/* Header */}
            <div
              className={`flex items-center gap-4 pb-3 border-b ${
                headerLayout === "logo-center"
                  ? "justify-center"
                  : headerLayout === "logo-right"
                  ? "flex-row-reverse"
                  : ""
              }`}
              style={{ borderColor: primaryColor + "30" }}
            >
              <div
                className="w-10 h-10 rounded flex items-center justify-center text-white text-[9px] font-bold"
                style={{ backgroundColor: primaryColor }}
              >
                LOGO
              </div>
              <div
                className={
                  headerLayout === "logo-center" ? "text-center" : ""
                }
              >
                <p
                  className="font-bold text-xs"
                  style={{ color: primaryColor }}
                >
                  OFERTĂ DE PREȚ
                </p>
                <p className="text-gray-400 text-[9px]">
                  #OFR-2024-001 · 15.02.2026
                </p>
              </div>
            </div>

            {/* Table */}
            <table className="w-full text-[9px]">
              <thead>
                <tr style={{ backgroundColor: primaryColor + "10" }}>
                  <th
                    className="text-left px-2 py-1.5 font-semibold"
                    style={{ color: primaryColor }}
                  >
                    Produs
                  </th>
                  <th
                    className="text-center px-2 py-1.5 font-semibold"
                    style={{ color: primaryColor }}
                  >
                    Cant.
                  </th>
                  {showPriceBreakdown && (
                    <th
                      className="text-right px-2 py-1.5 font-semibold"
                      style={{ color: primaryColor }}
                    >
                      Preț unit.
                    </th>
                  )}
                  <th
                    className="text-right px-2 py-1.5 font-semibold"
                    style={{ color: primaryColor }}
                  >
                    Total
                  </th>
                </tr>
              </thead>
              <tbody className="text-gray-600">
                <tr className="border-b border-gray-100">
                  <td className="px-2 py-1.5">Rucsac personalizat</td>
                  <td className="text-center px-2 py-1.5">100</td>
                  {showPriceBreakdown && (
                    <td className="text-right px-2 py-1.5">12.50 EUR</td>
                  )}
                  <td className="text-right px-2 py-1.5 font-medium">
                    1,250.00 EUR
                  </td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="px-2 py-1.5">Pix metalic gravat</td>
                  <td className="text-center px-2 py-1.5">500</td>
                  {showPriceBreakdown && (
                    <td className="text-right px-2 py-1.5">2.80 EUR</td>
                  )}
                  <td className="text-right px-2 py-1.5 font-medium">
                    1,400.00 EUR
                  </td>
                </tr>
              </tbody>
            </table>

            {/* Total */}
            <div className="flex justify-end">
              <div
                className="px-4 py-2 rounded text-white text-[10px] font-bold"
                style={{ backgroundColor: accentColor }}
              >
                TOTAL: 2,650.00 EUR
              </div>
            </div>

            {/* Footer */}
            {footerText && (
              <p className="text-[8px] text-gray-400 text-center pt-2 border-t border-gray-100">
                {footerText}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40 transition-all"
      >
        {saving ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Save size={14} />
        )}
        Salvează template
      </button>
    </div>
  );
}
