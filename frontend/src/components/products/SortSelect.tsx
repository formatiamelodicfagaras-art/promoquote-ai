"use client";

import { ArrowUpDown } from "lucide-react";

interface SortSelectProps {
  value: string;
  onChange: (sort: string) => void;
}

const SORT_OPTIONS = [
  { value: "", label: "Relevanță" },
  { value: "price_asc", label: "Preț crescător" },
  { value: "price_desc", label: "Preț descrescător" },
  { value: "name_asc", label: "Nume A-Z" },
  { value: "newest", label: "Cele mai noi" },
  { value: "stock", label: "Stoc disponibil" },
];

export default function SortSelect({ value, onChange }: SortSelectProps) {
  return (
    <div className="flex items-center gap-2">
      <ArrowUpDown className="w-4 h-4 text-gray-400 shrink-0" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700
                   focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 cursor-pointer"
      >
        {SORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
