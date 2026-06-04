"use client";

import { UNIFIED_COLOR_LIST } from "@/lib/brand-kit/color-mapping";
import { Check } from "lucide-react";

interface ColorPickerProps {
  selected: string[];
  onChange: (colors: string[]) => void;
}

export default function ColorPicker({ selected, onChange }: ColorPickerProps) {
  const toggle = (colorGroup: string) => {
    if (selected.includes(colorGroup)) {
      onChange(selected.filter((c) => c !== colorGroup));
    } else {
      onChange([...selected, colorGroup]);
    }
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Culori Brand
      </h3>
      <div className="flex flex-wrap gap-2">
        {UNIFIED_COLOR_LIST.map((color) => {
          const isSelected = selected.includes(color.colorGroup);
          return (
            <button
              key={color.key}
              onClick={() => toggle(color.colorGroup)}
              className={`
                relative flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                border transition-all
                ${
                  isSelected
                    ? "border-blue-500 bg-blue-50 text-blue-700 shadow-sm"
                    : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50"
                }
              `}
              title={color.label}
            >
              <span
                className="w-4 h-4 rounded-full border border-gray-300 flex-shrink-0"
                style={{ backgroundColor: color.hex }}
              />
              {color.label}
              {isSelected && <Check className="w-3 h-3 text-blue-600" />}
            </button>
          );
        })}
      </div>
      {selected.length > 0 && (
        <button
          onClick={() => onChange([])}
          className="mt-2 text-xs text-gray-400 hover:text-gray-600"
        >
          Resetează culori
        </button>
      )}
    </div>
  );
}
