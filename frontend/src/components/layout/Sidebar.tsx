"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  MessageSquare,
  FileText,
  Package,
  Settings,
  Plus,
  Clock,
  Palette,
  ShieldCheck,
  LogOut,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth-context";
import { fetchQuotes } from "@/lib/api";
import ThemeSelector from "@/components/layout/ThemeSelector";
import type { Quote } from "@/types";

const navigation = [
  { name: "Chat AI", href: "/chat", icon: MessageSquare, adminOnly: false },
  { name: "Oferte", href: "/quotes", icon: FileText, adminOnly: false },
  { name: "Produse", href: "/products", icon: Package, adminOnly: false },
  { name: "Packman AI", href: "/brand-kit", icon: Palette, adminOnly: false },
  { name: "Setari", href: "/settings", icon: Settings, adminOnly: true },
];

function relativeTime(iso?: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "acum";
  if (min < 60) return `acum ${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24) return `acum ${h}h`;
  const d = Math.floor(h / 24);
  if (d === 1) return "ieri";
  if (d < 7) return `${d} zile`;
  if (d < 30) return `${Math.floor(d / 7)} săpt`;
  return new Date(iso).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" });
}

function quoteLabel(q: Quote): string {
  const company = (q.client_company || "").trim();
  const name = (q.client_name || "").trim();
  const client = company || (name && name.toLowerCase() !== "client" ? name : "");
  if (client) return client;
  if (q.items?.[0]?.product_name) return q.items[0].product_name;
  return q.number || "Ofertă fără client";
}

interface SidebarProps {
  mobileOpen?: boolean;
  onClose?: () => void;
}

export default function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { clearChat } = useStore();
  const { user, isAdmin, logout } = useAuth();
  const [recentQuotes, setRecentQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchQuotes()
      .then((data) => {
        if (!cancelled) setRecentQuotes(data.slice(0, 5));
      })
      .catch(() => {
        if (!cancelled) setRecentQuotes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <aside
      className={`
        h-full bg-dark-800/50 backdrop-blur-xl border-r border-[--border] flex flex-col flex-shrink-0
        fixed top-0 left-0 z-50 w-[260px] transform transition-transform duration-200 ease-out
        md:static md:z-auto md:w-[240px] md:translate-x-0
        ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
      `}
    >
      {/* Logo */}
      <div className="p-5 pb-4 flex items-center justify-between">
        <Link href="/chat" onClick={onClose} className="flex items-center gap-2.5 group">
          <img src="/logo.svg" alt="PromoQuote AI" className="w-9 h-9 flex-shrink-0 rounded-lg" />
          <div>
            <h1 className="text-base font-bold text-dark-50 tracking-tight">
              PromoQuote AI
            </h1>
            <p className="text-[10px] text-dark-200 font-medium uppercase tracking-widest">
              AI Assistant
            </p>
          </div>
        </Link>
        <button
          onClick={onClose}
          className="md:hidden p-1.5 rounded-lg text-dark-300 hover:text-dark-50 hover:bg-dark-400/30 transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* New chat button */}
      <div className="px-3 mb-2">
        <button
          onClick={clearChat}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium bg-dark-500/40 border border-[--border] text-dark-100 hover:text-dark-50 hover:bg-dark-500/60 hover:border-accent/20 transition-all active:scale-[0.98]"
        >
          <Plus size={16} />
          Conversatie noua
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-3 py-2 space-y-0.5">
        {navigation.filter((item) => !item.adminOnly || isAdmin).map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
                isActive
                  ? "bg-accent/10 text-accent-hover border border-accent/10"
                  : "text-dark-100 hover:text-dark-50 hover:bg-dark-400/30 border border-transparent"
              )}
            >
              <item.icon size={18} />
              {item.name}
            </Link>
          );
        })}

        {/* Admin - only for admin users */}
        {isAdmin && (
          <Link
            href="/admin"
            className={cn(
              "flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
              pathname.startsWith("/admin")
                ? "bg-accent/10 text-accent-hover border border-accent/10"
                : "text-dark-100 hover:text-dark-50 hover:bg-dark-400/30 border border-transparent"
            )}
          >
            <ShieldCheck size={18} />
            Admin
          </Link>
        )}
      </nav>

      {/* Divider */}
      <div className="mx-4 my-3 h-px bg-[--border]" />

      {/* Recent quotes */}
      <div className="flex-1 overflow-y-auto px-3">
        <p className="text-[10px] text-dark-200 uppercase tracking-widest font-semibold px-3 mb-2">
          Oferte recente
        </p>
        <div className="space-y-0.5">
          {recentQuotes.length === 0 ? (
            <p className="text-[11px] text-dark-300 px-3 py-2">
              Nicio ofertă încă.
            </p>
          ) : (
            recentQuotes.map((quote) => (
              <Link
                key={quote.id}
                href={`/quotes/${quote.id}`}
                onClick={onClose}
                className="w-full flex items-start gap-2.5 px-3 py-2 rounded-xl text-left hover:bg-dark-400/20 transition-colors group"
              >
                <Clock
                  size={14}
                  className="text-dark-300 mt-0.5 flex-shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-dark-100 group-hover:text-dark-50 truncate transition-colors">
                    {quoteLabel(quote)}
                  </p>
                  <p className="text-[10px] text-dark-300">
                    {relativeTime(quote.created_at)}
                    {quote.total ? ` · ${quote.total.toFixed(0)} ${quote.currency}` : ""}
                  </p>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>

      {/* Footer - User info & logout */}
      <div className="p-4 border-t border-[--border]">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-7 h-7 flex-shrink-0 rounded-md bg-accent/10 flex items-center justify-center">
              <span className="text-xs font-bold text-accent">
                {user?.name?.charAt(0)?.toUpperCase() || "?"}
              </span>
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-dark-100 truncate">
                {user?.name || "Utilizator"}
              </p>
              <p className="text-[10px] text-dark-300 truncate">
                {user?.is_admin ? "Admin" : "Utilizator"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <ThemeSelector />
            <button
              onClick={logout}
              title="Deconectare"
              className="p-1.5 rounded-lg text-dark-300 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
