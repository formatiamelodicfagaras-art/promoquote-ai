"use client";

import { useEffect, useRef, useState } from "react";
import { fetchClientSuggestions, type ClientSuggestion } from "@/lib/api";

interface ClientAutocompleteProps {
  /** Which field this input edits — drives which value is used for the search query. */
  field: "client_name" | "client_company" | "client_email";
  value: string;
  onChange: (value: string) => void;
  /** Called when user picks a suggestion — receives the full client triple. */
  onPick: (s: ClientSuggestion) => void;
  placeholder: string;
  className?: string;
  /** Optional: onBlur callback so existing patches-on-blur still work. */
  onBlur?: () => void;
}

export default function ClientAutocomplete({
  field,
  value,
  onChange,
  onPick,
  placeholder,
  className,
  onBlur,
}: ClientAutocompleteProps) {
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<ClientSuggestion[]>([]);
  const [activeIdx, setActiveIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced fetch
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const data = await fetchClientSuggestions(value || undefined, 8);
      setSuggestions(data);
      setActiveIdx(-1);
    }, 150);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value, open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const pick = (s: ClientSuggestion) => {
    onPick(s);
    setOpen(false);
  };

  const visible = suggestions.filter((s) => {
    const own = s[field];
    if (!own) return false;
    if (!value.trim()) return true;
    return own.toLowerCase().includes(value.toLowerCase()) ||
      `${s.client_name} ${s.client_company} ${s.client_email}`
        .toLowerCase()
        .includes(value.toLowerCase());
  });

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Delay so onClick on a suggestion fires first
          setTimeout(() => {
            setOpen(false);
            onBlur?.();
          }, 150);
        }}
        onKeyDown={(e) => {
          if (!open || visible.length === 0) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIdx((i) => (i + 1) % visible.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIdx((i) => (i <= 0 ? visible.length - 1 : i - 1));
          } else if (e.key === "Enter" && activeIdx >= 0) {
            e.preventDefault();
            pick(visible[activeIdx]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder={placeholder}
        className={className}
      />
      {open && visible.length > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 max-h-64 overflow-y-auto rounded-lg border border-[rgba(255,255,255,0.08)] bg-dark-700/95 backdrop-blur-xl shadow-2xl">
          {visible.map((s, idx) => {
            const primary = s.client_company || s.client_name || s.client_email;
            const secondary = [
              s.client_company ? s.client_name : null,
              s.client_email,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <button
                key={`${s.client_name}|${s.client_company}|${s.client_email}|${idx}`}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(s)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                  idx === activeIdx
                    ? "bg-accent/15 text-dark-50"
                    : "text-dark-100 hover:bg-dark-400/40"
                }`}
              >
                <div className="font-medium truncate">{primary}</div>
                {secondary && (
                  <div className="text-[10px] text-dark-300 truncate">
                    {secondary}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
