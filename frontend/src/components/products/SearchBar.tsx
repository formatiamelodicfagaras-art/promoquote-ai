"use client";

import { useState, useRef, useEffect } from "react";
import { Search, X, Package } from "lucide-react";

export interface Suggestion {
  name: string;
  code: string;
  category: string;
  image?: string;
  highlighted_name?: string;
  highlighted_code?: string;
}

interface SearchBarProps {
  value: string;
  onChange: (q: string) => void;
  suggestions: Suggestion[];
  loading?: boolean;
}

export default function SearchBar({
  value,
  onChange,
  suggestions,
  loading,
}: SearchBarProps) {
  const [focused, setFocused] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const showDropdown = focused && suggestions.length > 0 && value.length >= 2;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target as Node)
      ) {
        setFocused(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={wrapperRef} className="relative w-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          placeholder="Caută produse sau coduri (ex: tricouri, 100, MO-S00553)..."
          className="w-full pl-11 pr-10 py-3 rounded-xl border border-gray-200 bg-white
                     text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400
                     transition-all placeholder:text-gray-400"
        />
        {value && (
          <button
            onClick={() => onChange("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X className="w-4 h-4" />
          </button>
        )}
        {loading && (
          <div className="absolute right-10 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 mt-1 w-full bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden max-h-[420px] overflow-y-auto">
          {suggestions.map((s, i) => (
            <button
              key={`${s.code}-${i}`}
              className="w-full text-left px-3 py-2.5 text-sm hover:bg-blue-50 flex items-center gap-3 transition-colors border-b border-gray-50 last:border-0"
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(s.code || s.name);
                setFocused(false);
              }}
            >
              {/* Thumbnail */}
              {s.image ? (
                <img
                  src={s.image}
                  alt=""
                  className="w-9 h-9 rounded object-contain bg-gray-50 flex-shrink-0"
                />
              ) : (
                <div className="w-9 h-9 rounded bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <Package className="w-4 h-4 text-gray-300" />
                </div>
              )}
              {/* Text */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-sm text-gray-900 truncate"
                    dangerouslySetInnerHTML={{
                      __html: s.highlighted_name || s.name,
                    }}
                  />
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  {s.code && (
                    <span
                      className="text-[11px] font-mono text-blue-600 font-medium"
                      dangerouslySetInnerHTML={{
                        __html: s.highlighted_code || s.code,
                      }}
                    />
                  )}
                  {s.category && (
                    <span className="text-[11px] text-gray-400">
                      {s.category}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
