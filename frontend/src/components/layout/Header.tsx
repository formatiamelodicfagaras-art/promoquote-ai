"use client";

import { usePathname } from "next/navigation";
import { useStore } from "@/lib/store";
import { FileText, Trash2, Menu } from "lucide-react";
import { cn } from "@/lib/cn";
import HeaderCategoryMenu from "@/components/products/HeaderCategoryMenu";
import { useMobileSidebar } from "./ClientShell";

const titles: Record<string, string> = {
  "/chat": "Chat AI",
  "/quotes": "Oferte",
  "/products": "Catalog Produse",
  "/settings": "Setări",
};

export default function Header() {
  const pathname = usePathname();
  const { currentQuote, draftItems, toggleQuotePanel, isQuotePanelOpen, clearChat, messages } =
    useStore();
  const { toggle: toggleSidebar } = useMobileSidebar();
  const hasQuoteContent = draftItems.length > 0 || currentQuote;
  const quoteItemCount = draftItems.length > 0 ? draftItems.length : (currentQuote?.items?.length || 0);

  const title =
    Object.entries(titles).find(([key]) => pathname.startsWith(key))?.[1] ??
    "PromoQuote AI";

  const isChat = pathname.startsWith("/chat");
  const isProducts = pathname.startsWith("/products");

  return (
    <header className="relative min-h-12 bg-slate-900 border-b border-slate-700/50 flex items-center justify-between px-3 md:px-5 py-1.5 z-30">
      <div className="flex items-center gap-2 md:gap-4 min-w-0 flex-1">
        <button
          onClick={toggleSidebar}
          className="md:hidden p-1.5 rounded-lg text-dark-200 hover:text-white hover:bg-dark-400/30 transition-colors flex-shrink-0"
        >
          <Menu size={20} />
        </button>
        <h2 className="text-sm font-bold text-white flex-shrink-0 tracking-tight">{title}</h2>
        {isProducts && <HeaderCategoryMenu />}
      </div>

      {isChat && (
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium text-dark-200 hover:text-dark-50 hover:bg-dark-400/30 transition-all"
            >
              <Trash2 size={12} />
              Șterge chat
            </button>
          )}

          {hasQuoteContent && (
            <button
              onClick={toggleQuotePanel}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all",
                isQuotePanelOpen
                  ? "bg-accent/10 text-accent-hover"
                  : "text-dark-200 hover:text-dark-50 hover:bg-dark-400/30"
              )}
            >
              <FileText size={12} />
              Ofertă
              {quoteItemCount > 0 && (
                <span className="ml-1 w-4 h-4 rounded-full bg-accent/20 text-accent text-[10px] flex items-center justify-center font-bold">
                  {quoteItemCount}
                </span>
              )}
            </button>
          )}
        </div>
      )}
    </header>
  );
}
