"use client";

import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import QuotePanel from "@/components/quotes/QuotePanel";
import { useStore } from "@/lib/store";
import { AnimatePresence } from "framer-motion";
import { FileText } from "lucide-react";

export default function ChatPage() {
  const { currentQuote, draftItems, isQuotePanelOpen, toggleQuotePanel } = useStore();
  const hasContent = draftItems.length > 0 || currentQuote;
  const itemCount = draftItems.length > 0 ? draftItems.length : (currentQuote?.items?.length || 0);

  return (
    <div className="flex h-full gradient-mesh relative">
      {/* Quote panel — LEFT side */}
      <AnimatePresence>
        {isQuotePanelOpen && hasContent && <QuotePanel />}
      </AnimatePresence>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        <MessageList />
        <ChatInput />
      </div>

      {/* FAB button when quote is hidden */}
      {hasContent && !isQuotePanelOpen && (
        <button
          onClick={toggleQuotePanel}
          className="absolute left-4 bottom-28 w-12 h-12 rounded-2xl bg-accent text-white flex items-center justify-center shadow-lg glow-accent hover:bg-accent-hover transition-all active:scale-90 z-10"
          title="Deschide oferta"
        >
          <FileText size={20} />
          {itemCount > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-success text-white text-[10px] font-bold flex items-center justify-center">
              {itemCount}
            </span>
          )}
        </button>
      )}
    </div>
  );
}
