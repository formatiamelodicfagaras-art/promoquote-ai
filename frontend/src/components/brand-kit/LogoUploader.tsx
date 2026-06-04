"use client";

import { useRef, useState } from "react";
import { Upload, X, Image as ImageIcon } from "lucide-react";
import { uploadLogo, getLogoUrl } from "@/lib/brand-kit/api";

interface LogoUploaderProps {
  logoUrl: string | null;
  onLogoChange: (url: string | null, base64: string | null) => void;
}

export default function LogoUploader({ logoUrl, onLogoChange }: LogoUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (file: File) => {
    if (!file.type.includes("png")) {
      alert("Doar fișiere PNG sunt acceptate");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("Fișierul depășește 5MB");
      return;
    }

    // Read base64
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = reader.result as string;
      setUploading(true);
      try {
        const result = await uploadLogo(file);
        onLogoChange(getLogoUrl(result.filename), base64);
      } catch {
        // Fallback: use base64 directly
        onLogoChange(base64, base64);
      } finally {
        setUploading(false);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Logo Client</h3>

      {logoUrl ? (
        <div className="relative inline-block">
          <img
            src={logoUrl}
            alt="Logo"
            className="h-20 max-w-[200px] object-contain bg-gray-50 rounded-lg border border-gray-200 p-2"
          />
          <button
            onClick={() => onLogoChange(null, null)}
            className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`
            flex flex-col items-center justify-center gap-2 p-6 rounded-xl border-2 border-dashed cursor-pointer transition-all
            ${dragOver ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"}
          `}
        >
          {uploading ? (
            <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
          ) : (
            <>
              <Upload className="w-8 h-8 text-gray-300" />
              <p className="text-xs text-gray-500">
                Click sau drag & drop — PNG, max 5MB
              </p>
            </>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/png"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
    </div>
  );
}
