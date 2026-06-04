"use client";

import { useMemo, useState, useEffect } from "react";
import { ChevronDown, FolderOpen, Folder } from "lucide-react";
import QuoteList from "./QuoteList";
import type { Quote } from "@/types";

interface QuoteFoldersProps {
  quotes: Quote[];
  searchActive: boolean;
  onDelete?: (id: string) => void;
  onUpdate?: (quote: Quote) => void;
}

const NO_CLIENT_KEY = "__no_client__";
const NO_CLIENT_LABEL = "Fără client";

const COMPANY_SUFFIX_RE =
  /\s+(s\.?r\.?l\.?|s\.?a\.?|p\.?f\.?a\.?|i\.?i\.?|ltd|llc|gmbh|inc|s\.?c\.?a\.?)\.?\s*$/i;

/** Lowercase + strip diacritics + strip company suffix + collapse spaces. */
function normalizeForGroup(s: string): string {
  let out = s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toLowerCase();
  let prev = "";
  while (out !== prev) {
    prev = out;
    out = out.replace(COMPANY_SUFFIX_RE, "").trim();
  }
  return out.replace(/\s+/g, " ");
}

function rawClientName(q: Quote): string {
  const company = (q.client_company || "").trim();
  if (company) return company;
  const name = (q.client_name || "").trim();
  if (name && name.toLowerCase() !== "client") return name;
  return "";
}

function folderKey(q: Quote): string {
  const raw = rawClientName(q);
  if (!raw) return NO_CLIENT_KEY;
  const norm = normalizeForGroup(raw);
  return norm || NO_CLIENT_KEY;
}

export default function QuoteFolders({
  quotes,
  searchActive,
  onDelete,
  onUpdate,
}: QuoteFoldersProps) {
  const groups = useMemo(() => {
    const map = new Map<string, Quote[]>();
    for (const q of quotes) {
      const key = folderKey(q);
      const arr = map.get(key) || [];
      arr.push(q);
      map.set(key, arr);
    }

    const entries = Array.from(map.entries()).map(([key, qs]) => {
      qs.sort((a, b) => {
        const da = a.created_at ? new Date(a.created_at).getTime() : 0;
        const db = b.created_at ? new Date(b.created_at).getTime() : 0;
        return db - da;
      });
      const total = qs.reduce((sum, q) => sum + (q.total || 0), 0);
      const currency = qs[0]?.currency || "EUR";
      // Label = the longest non-empty raw client name in the group
      let label = NO_CLIENT_LABEL;
      if (key !== NO_CLIENT_KEY) {
        const variants = qs
          .map((q) => rawClientName(q))
          .filter((s) => s.length > 0);
        label = variants.reduce(
          (best, cur) => (cur.length > best.length ? cur : best),
          variants[0] || "",
        );
      }
      return { key, label, quotes: qs, total, currency };
    });

    entries.sort((a, b) => {
      if (a.key === NO_CLIENT_KEY) return 1;
      if (b.key === NO_CLIENT_KEY) return -1;
      return a.label.localeCompare(b.label, "ro", { sensitivity: "base" });
    });

    return entries;
  }, [quotes]);

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (searchActive) {
      setExpanded(new Set(groups.map((g) => g.key)));
    } else {
      setExpanded(new Set());
    }
  }, [searchActive, groups]);

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="space-y-2">
      {groups.map((group) => {
        const isOpen = expanded.has(group.key);
        return (
          <div
            key={group.key}
            className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-dark-500/10 overflow-hidden"
          >
            <button
              onClick={() => toggle(group.key)}
              className="w-full flex items-center justify-between gap-3 px-3 sm:px-4 py-3 hover:bg-dark-500/30 transition-colors text-left"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <ChevronDown
                  size={16}
                  className={`text-dark-300 flex-shrink-0 transition-transform ${
                    isOpen ? "" : "-rotate-90"
                  }`}
                />
                {isOpen ? (
                  <FolderOpen size={18} className="text-accent flex-shrink-0" />
                ) : (
                  <Folder size={18} className="text-dark-200 flex-shrink-0" />
                )}
                <span className="font-semibold text-sm text-dark-50 truncate">
                  {group.label}
                </span>
                <span className="text-[11px] text-dark-300 font-medium flex-shrink-0">
                  {group.quotes.length}{" "}
                  {group.quotes.length === 1 ? "ofertă" : "oferte"}
                </span>
              </div>
              <span className="text-xs sm:text-sm font-bold text-accent flex-shrink-0">
                {group.total.toFixed(2)} {group.currency}
              </span>
            </button>

            {isOpen && (
              <div className="px-2 sm:px-3 pb-2 pt-1">
                <QuoteList
                  quotes={group.quotes}
                  onDelete={onDelete}
                  onUpdate={onUpdate}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
