"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTheme, type Theme } from "@/lib/theme";
import { Palette, Check } from "lucide-react";

const themes: {
  id: Theme;
  label: string;
  subtitle: string;
  bg: string;
  accent: string;
  accentGradient?: string;
}[] = [
  {
    id: "dark",
    label: "Întuneric",
    subtitle: "Indigo glassmorphism",
    bg: "#0a0a0f",
    accent: "#6366f1",
  },
  {
    id: "light",
    label: "Luminos",
    subtitle: "Apple clean whites",
    bg: "#ffffff",
    accent: "#007aff",
  },
  {
    id: "frost",
    label: "Frost",
    subtitle: "Modern teal accent",
    bg: "#fbfbfe",
    accent: "#0d9488",
  },
  {
    id: "sequoia",
    label: "Sequoia",
    subtitle: "Apple premium, indigo→purple",
    bg: "#f5f5f7",
    accent: "#5856d6",
    accentGradient: "linear-gradient(135deg, #5856d6, #af52de)",
  },
  {
    id: "graphite",
    label: "Grafit",
    subtitle: "Warm dark, orange",
    bg: "#000000",
    accent: "#ff9f0a",
  },
];

export default function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: 0, bottom: 0 });

  const updatePos = useCallback(() => {
    if (btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setPos({
        left: rect.left,
        bottom: window.innerHeight - rect.top + 8,
      });
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePos();
    const handler = (e: MouseEvent) => {
      if (
        dropRef.current &&
        !dropRef.current.contains(e.target as Node) &&
        btnRef.current &&
        !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, updatePos]);

  const current = themes.find((t) => t.id === theme) ?? themes[0];

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-all duration-200 hover:bg-dark-400/30"
        title="Schimbă tema"
      >
        <Palette size={15} className="text-accent" />
        <span className="text-xs font-medium text-dark-100">
          {current.label}
        </span>
      </button>

      {open &&
        createPortal(
          <div
            ref={dropRef}
            className="fixed w-60 rounded-xl border border-[var(--border-strong)] bg-[var(--c-800)] shadow-2xl shadow-black/30 overflow-hidden"
            style={{
              left: pos.left,
              bottom: pos.bottom,
              zIndex: 9999,
            }}
          >
            <div className="px-3 py-2 border-b border-[var(--border)]">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-dark-200">
                Temă
              </p>
            </div>
            <div className="p-1.5 space-y-0.5">
              {themes.map((t) => {
                const active = theme === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      setTheme(t.id);
                      setOpen(false);
                    }}
                    className={`
                      w-full flex items-center gap-3 px-2.5 py-2.5 rounded-lg transition-all duration-150
                      ${active ? "bg-accent/10" : "hover:bg-dark-400/20"}
                    `}
                  >
                    <div className="flex items-center -space-x-1.5 shrink-0">
                      <div
                        className="w-6 h-6 rounded-full border-2 border-white/20"
                        style={{ backgroundColor: t.bg, boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }}
                      />
                      <div
                        className="w-6 h-6 rounded-full border-2 border-white/20"
                        style={{
                          background: t.accentGradient ?? t.accent,
                          boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                        }}
                      />
                    </div>

                    <div className="flex-1 text-left min-w-0">
                      <p
                        className={`text-sm font-medium leading-tight ${
                          active ? "text-accent" : "text-dark-50"
                        }`}
                      >
                        {t.label}
                      </p>
                      <p className="text-[11px] text-dark-200 leading-tight">
                        {t.subtitle}
                      </p>
                    </div>

                    {active && (
                      <Check size={16} className="text-accent shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
