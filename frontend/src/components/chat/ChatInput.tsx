"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Sparkles, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { useStore } from "@/lib/store";
import { sendChatMessage, fetchQuote, addQuoteItem } from "@/lib/api";
import type { Product } from "@/types";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

const QUICK_SUGGESTIONS = [
  { label: "Cadouri 8 Martie", icon: "🌷" },
  { label: "Produse cu logo", icon: "🏷️" },
  { label: "Ofertă urgentă", icon: "⚡" },
  { label: "Rucsacuri/Genți", icon: "🎒" },
];

export default function ChatInput() {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    messages,
    addMessage,
    currentQuote,
    isAiTyping,
    setIsAiTyping,
    setStreamingContent,
    appendStreamingContent,
    setCurrentQuote,
    appendQuoteAsDraft,
  } = useStore();

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || isAiTyping) return;

    setInput("");
    addMessage({ role: "user", content: message });
    setIsAiTyping(true);
    setStreamingContent("");

    try {
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      let assistantText = "";

      await sendChatMessage(
        message,
        history,
        currentQuote?.id != null ? Number(currentQuote.id) : null,
        (event) => {
          if (event.type === "text") {
            assistantText += event.content as string;
            appendStreamingContent(event.content as string);
          } else if (event.type === "products") {
            // Products are informational; quote is created separately
          } else if (event.type === "quote_update") {
            const data = event.content as Record<string, unknown>;
            const quoteId = data.quote_id as string;
            if (quoteId) {
              fetchQuote(quoteId as unknown as number).then(async (quote) => {
                const state = useStore.getState();
                const hasDraft = state.draftItems.length > 0;
                const existingQuote = state.currentQuote;

                if (hasDraft) {
                  // Draft is active — append AI items into it,
                  // discard the AI-created temp quote.
                  appendQuoteAsDraft(quote);
                  fetch(`${API}/quotes/${quote.id}`, { method: "DELETE" })
                    .catch(() => {});
                } else if (existingQuote && existingQuote.id !== quote.id) {
                  // User has an existing saved quote loaded — append AI items
                  // to it via API, then discard the AI temp quote.
                  try {
                    let updated = existingQuote;
                    for (const item of quote.items) {
                      updated = await addQuoteItem(existingQuote.id, {
                        product_id: item.product_id,
                        product_name: item.product_name,
                        product_sku: item.product_sku,
                        product_color: item.product_color,
                        product_image: item.product_image,
                        product_size: item.product_size,
                        quantity: item.quantity,
                        unit_price: item.unit_price,
                        margin_percent: item.margin_percent,
                        printing_method: item.printing_method,
                        printing_cost: item.printing_cost,
                        printing_setup: item.printing_setup,
                        customization_notes: item.customization_notes,
                      });
                    }
                    setCurrentQuote(updated);
                    fetch(`${API}/quotes/${quote.id}`, { method: "DELETE" })
                      .catch(() => {});
                  } catch (err) {
                    console.error("Failed to append AI items to existing quote:", err);
                    setCurrentQuote(quote);
                  }
                } else {
                  setCurrentQuote(quote);
                }
              });
            }
          } else if (event.type === "done") {
            if (assistantText) {
              addMessage({ role: "assistant", content: assistantText });
            }
          }
        }
      );
    } catch {
      addMessage({
        role: "assistant",
        content: "A apărut o eroare. Te rog încearcă din nou.",
      });
    }

    setIsAiTyping(false);
    setStreamingContent("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const showSuggestions = messages.length === 0 && !input;

  return (
    <div className="border-t border-[rgba(255,255,255,0.06)] bg-dark-900/80 backdrop-blur-xl">
      {/* AI typing indicator */}
      <AnimatePresence>
        {isAiTyping && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="px-6 py-2 flex items-center gap-2 text-xs text-dark-200"
          >
            <Loader2 size={12} className="animate-spin text-accent" />
            <span>PromoQuote AI scrie...</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Quick suggestions */}
      <AnimatePresence>
        {showSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="px-3 sm:px-6 pt-3 sm:pt-4 pb-2 flex flex-wrap gap-2"
          >
            {QUICK_SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion.label}
                onClick={() => handleSend(suggestion.label)}
                className="flex items-center gap-2 px-4 py-2 rounded-2xl text-sm bg-dark-500/60 border border-[rgba(255,255,255,0.06)] text-dark-100 hover:text-dark-50 hover:border-accent/30 hover:bg-accent/5 transition-all active:scale-95"
              >
                <span>{suggestion.icon}</span>
                {suggestion.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input area */}
      <div className="p-2 sm:p-4 max-w-4xl mx-auto">
        <div className="relative flex items-end gap-2 bg-dark-600/50 border border-[rgba(255,255,255,0.08)] rounded-2xl p-2 focus-within:border-accent/30 focus-within:shadow-lg focus-within:shadow-accent/5 transition-all">
          <Sparkles
            size={16}
            className="absolute left-4 top-1/2 -translate-y-1/2 text-dark-200 pointer-events-none"
          />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Descrie ce produse promoționale cauți..."
            disabled={isAiTyping}
            rows={1}
            className={cn(
              "flex-1 bg-transparent resize-none outline-none text-sm text-dark-50 placeholder:text-dark-200",
              "pl-8 pr-2 py-2 max-h-40",
              "disabled:opacity-50"
            )}
          />
          <button
            onClick={() => handleSend()}
            disabled={isAiTyping || !input.trim()}
            className={cn(
              "flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all",
              input.trim() && !isAiTyping
                ? "bg-accent text-white hover:bg-accent-hover active:scale-90 glow-accent"
                : "bg-dark-400/40 text-dark-200 cursor-not-allowed"
            )}
          >
            {isAiTyping ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-dark-200 text-center mt-2">
          PromoQuote AI poate face greșeli. Verifică întotdeauna prețurile.
        </p>
      </div>
    </div>
  );
}
