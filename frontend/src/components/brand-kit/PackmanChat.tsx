"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Loader2,
  Palette,
  Bot,
  User,
  Package,
  Plus,
  Check,
  Eye,
  FileDown,
} from "lucide-react";
import { cn } from "@/lib/cn";
import type { BrandKitProduct } from "@/lib/brand-kit/types";
import {
  sendPackmanMessage,
  generatePdf,
  type PackmanChatEvent,
} from "@/lib/brand-kit/api";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

interface PackmanMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  products?: BrandKitProduct[];
}

interface PackmanChatProps {
  brandColors: string[];
  logoUrl: string | null;
  logoBase64: string | null;
  clientName: string;
  companyId?: string;
  selectedProducts: BrandKitProduct[];
  mockups: Record<string, string>;
  onToggleProduct: (product: BrandKitProduct) => void;
  onOpenMockup: (product: BrandKitProduct) => void;
  isProductSelected: (id: string) => boolean;
}

const QUICK_SUGGESTIONS = [
  { label: "Geacă, notebook și pix metalic", icon: "🧥" },
  { label: "Rucsac cu accesorii birou", icon: "🎒" },
  { label: "Pachet cadou corporate premium", icon: "🎁" },
  { label: "Set conferință complet", icon: "📋" },
  { label: "Tricou, șapcă și sticlă sport", icon: "👕" },
];

let msgCounter = 0;

export default function PackmanChat({
  brandColors,
  logoUrl,
  logoBase64,
  clientName,
  companyId,
  selectedProducts,
  mockups,
  onToggleProduct,
  onOpenMockup,
  isProductSelected,
}: PackmanChatProps) {
  const [messages, setMessages] = useState<PackmanMessage[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingProducts, setStreamingProducts] = useState<BrandKitProduct[]>([]);
  const [generatingPdf, setGeneratingPdf] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const historyRef = useRef<{ role: string; content: string }[]>([]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping, streamingContent, streamingProducts]);

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => { adjustHeight(); }, [input, adjustHeight]);

  const handleSend = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isTyping) return;

    setInput("");
    const userMsg: PackmanMessage = {
      id: `pm-${++msgCounter}-${Date.now()}`,
      role: "user",
      content: msg,
    };
    setMessages((prev) => [...prev, userMsg]);
    historyRef.current.push({ role: "user", content: msg });

    setIsTyping(true);
    setStreamingContent("");
    setStreamingProducts([]);

    let assistantText = "";
    let collectedProducts: BrandKitProduct[] = [];

    try {
      await sendPackmanMessage(
        msg,
        historyRef.current.slice(0, -1), // don't send current message in history
        brandColors,
        (event: PackmanChatEvent) => {
          if (event.type === "text") {
            assistantText += event.content as string;
            setStreamingContent((prev) => prev + (event.content as string));
          } else if (event.type === "products") {
            const prods = event.content as BrandKitProduct[];
            collectedProducts = [...collectedProducts, ...prods];
            setStreamingProducts([...collectedProducts]);
          } else if (event.type === "done") {
            const assistantMsg: PackmanMessage = {
              id: `pm-${++msgCounter}-${Date.now()}`,
              role: "assistant",
              content: assistantText,
              products: collectedProducts.length > 0 ? collectedProducts : undefined,
            };
            setMessages((prev) => [...prev, assistantMsg]);
            historyRef.current.push({ role: "assistant", content: assistantText });
            setStreamingContent("");
            setStreamingProducts([]);
          }
        },
      );
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `pm-${++msgCounter}-${Date.now()}`,
          role: "assistant",
          content: "A apărut o eroare. Te rog încearcă din nou.",
        },
      ]);
    }

    setIsTyping(false);
    setStreamingContent("");
    setStreamingProducts([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleGeneratePdf = async () => {
    if (selectedProducts.length === 0) return;
    setGeneratingPdf(true);
    try {
      const pdfProducts = selectedProducts.map((p) => ({
        sku: p.sku,
        supplier: p.supplier,
        name: p.name,
        mockup_base64: mockups[p.id] || "",
        image_url: p.image_url || "",
        colors: p.color ? [p.color] : [],
        print_method: p.print_areas[0]?.method || "",
        print_area: p.print_areas[0]?.location || "",
        print_dimensions: p.print_areas[0]
          ? `${p.print_areas[0].width_mm}×${p.print_areas[0].height_mm}mm`
          : "",
        min_order: p.min_order,
      }));
      const result = await generatePdf({
        client_name: clientName,
        company_id: companyId || "",
        selected_products: pdfProducts,
        logo_base64: logoBase64 || "",
      });
      window.open(result.pdf_url, "_blank");
    } catch {
      alert("Eroare la generarea PDF-ului");
    } finally {
      setGeneratingPdf(false);
    }
  };

  const showSuggestions = messages.length === 0 && !input;

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
          {messages.length === 0 && !isTyping && <EmptyState />}

          <AnimatePresence mode="popLayout">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                logoUrl={logoUrl}
                onToggleProduct={onToggleProduct}
                onOpenMockup={onOpenMockup}
                isProductSelected={isProductSelected}
              />
            ))}
          </AnimatePresence>

          {/* Streaming content */}
          {streamingContent && (
            <StreamingBubble content={streamingContent} />
          )}

          {/* Streaming products */}
          {streamingProducts.length > 0 && (
            <ProductCards
              products={streamingProducts}
              logoUrl={logoUrl}
              onToggleProduct={onToggleProduct}
              onOpenMockup={onOpenMockup}
              isProductSelected={isProductSelected}
            />
          )}

          {/* Typing indicator */}
          <AnimatePresence>
            {isTyping && !streamingContent && <TypingIndicator />}
          </AnimatePresence>

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Selected products bar */}
      {selectedProducts.length > 0 && (
        <div className="border-t border-[rgba(255,255,255,0.06)] bg-dark-800/80 backdrop-blur-xl px-4 py-2">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-dark-200">
                {selectedProducts.length} produse selectate
              </span>
              <div className="flex -space-x-2">
                {selectedProducts.slice(0, 5).map((p) => (
                  <img
                    key={p.id}
                    src={mockups[p.id] || p.image_url}
                    alt=""
                    className="w-7 h-7 rounded-lg border-2 border-dark-700 bg-white object-contain"
                  />
                ))}
                {selectedProducts.length > 5 && (
                  <span className="w-7 h-7 rounded-lg border-2 border-dark-700 bg-dark-600 flex items-center justify-center text-[10px] text-dark-200">
                    +{selectedProducts.length - 5}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={handleGeneratePdf}
              disabled={generatingPdf}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50"
            >
              <FileDown className="w-3.5 h-3.5" />
              {generatingPdf ? "Se generează..." : "Descarcă PDF"}
            </button>
          </div>
        </div>
      )}

      {/* Quick suggestions */}
      <AnimatePresence>
        {showSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="px-6 pt-4 pb-2 flex flex-wrap gap-2 justify-center"
          >
            {QUICK_SUGGESTIONS.map((s) => (
              <button
                key={s.label}
                onClick={() => handleSend(s.label)}
                className="flex items-center gap-2 px-4 py-2 rounded-2xl text-sm bg-dark-500/60 border border-[rgba(255,255,255,0.06)] text-dark-100 hover:text-dark-50 hover:border-accent/30 hover:bg-accent/5 transition-all active:scale-95"
              >
                <span>{s.icon}</span>
                {s.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input area */}
      <div className="border-t border-[rgba(255,255,255,0.06)] bg-dark-900/80 backdrop-blur-xl">
        <AnimatePresence>
          {isTyping && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="px-6 py-2 flex items-center gap-2 text-xs text-dark-200"
            >
              <Loader2 size={12} className="animate-spin text-accent" />
              <span>PACKMAN AI caută produse...</span>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="p-4 max-w-4xl mx-auto">
          <div className="relative flex items-end gap-2 bg-dark-600/50 border border-[rgba(255,255,255,0.08)] rounded-2xl p-2 focus-within:border-accent/30 focus-within:shadow-lg focus-within:shadow-accent/5 transition-all">
            <Palette
              size={16}
              className="absolute left-4 top-1/2 -translate-y-1/2 text-dark-200 pointer-events-none"
            />
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Descrie ce produse vrei în pachet... (ex: geacă, notebook, pix metalic)"
              disabled={isTyping}
              rows={1}
              className={cn(
                "flex-1 bg-transparent resize-none outline-none text-sm text-dark-50 placeholder:text-dark-200",
                "pl-8 pr-2 py-2 max-h-40",
                "disabled:opacity-50",
              )}
            />
            <button
              onClick={() => handleSend()}
              disabled={isTyping || !input.trim()}
              className={cn(
                "flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all",
                input.trim() && !isTyping
                  ? "bg-accent text-white hover:bg-accent-hover active:scale-90 glow-accent"
                  : "bg-dark-400/40 text-dark-200 cursor-not-allowed",
              )}
            >
              {isTyping ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
            </button>
          </div>
          <p className="text-[10px] text-dark-200 text-center mt-2">
            PACKMAN AI generează propuneri creative — fără prețuri, doar idei vizuale
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center min-h-[300px]">
      <div className="text-center max-w-md px-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-600/20 flex items-center justify-center mx-auto mb-6">
          <Palette size={28} className="text-accent" />
        </div>
        <h2 className="text-xl font-semibold text-dark-50 mb-2">
          PACKMAN AI
        </h2>
        <p className="text-sm text-dark-200 leading-relaxed">
          Spune-mi ce produse dorești în pachetul promoțional. Voi căuta produse
          în culorile brand-ului tău și voi genera mockup-uri cu logo-ul.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {["Geacă cu logo", "Set birou", "Cadou corporate"].map((ex) => (
            <span
              key={ex}
              className="px-3 py-1.5 rounded-full text-xs bg-dark-500/40 border border-[rgba(255,255,255,0.06)] text-dark-200"
            >
              {ex}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  logoUrl,
  onToggleProduct,
  onOpenMockup,
  isProductSelected,
}: {
  message: PackmanMessage;
  logoUrl: string | null;
  onToggleProduct: (p: BrandKitProduct) => void;
  onOpenMockup: (p: BrandKitProduct) => void;
  isProductSelected: (id: string) => boolean;
}) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn("flex gap-3 group", isUser ? "flex-row-reverse" : "")}
    >
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center mt-1",
          isUser
            ? "bg-accent text-white"
            : "bg-gradient-to-br from-purple-500/30 to-blue-600/30 border border-[rgba(255,255,255,0.08)] text-accent-hover",
        )}
      >
        {isUser ? <User size={16} /> : <Palette size={16} />}
      </div>

      <div className={cn("max-w-[80%] space-y-3", isUser ? "items-end" : "")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-[14px] leading-relaxed",
            isUser
              ? "bg-accent text-white rounded-tr-md"
              : "bg-dark-500 border border-[rgba(255,255,255,0.06)] text-dark-50 rounded-tl-md shadow-lg shadow-black/10",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="ai-markdown">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Product cards */}
        {message.products && message.products.length > 0 && (
          <ProductCards
            products={message.products}
            logoUrl={logoUrl}
            onToggleProduct={onToggleProduct}
            onOpenMockup={onOpenMockup}
            isProductSelected={isProductSelected}
          />
        )}
      </div>
    </motion.div>
  );
}

function StreamingBubble({ content }: { content: string }) {
  if (!content) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-purple-500/30 to-blue-600/30 border border-[rgba(255,255,255,0.08)] text-accent-hover">
        <Palette size={16} />
      </div>
      <div className="max-w-[80%] bg-dark-500 border border-[rgba(255,255,255,0.06)] rounded-2xl rounded-tl-md px-4 py-3 shadow-lg shadow-black/10">
        <div className="ai-markdown text-[14px] leading-relaxed text-dark-50">
          <ReactMarkdown>{content}</ReactMarkdown>
          <span className="inline-block w-2 h-4 bg-accent-hover/70 animate-pulse ml-0.5 -mb-0.5 rounded-sm" />
        </div>
      </div>
    </motion.div>
  );
}

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex gap-3"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-purple-500/30 to-blue-600/30 border border-[rgba(255,255,255,0.08)] text-accent-hover">
        <Palette size={16} />
      </div>
      <div className="bg-dark-500 border border-[rgba(255,255,255,0.06)] rounded-2xl rounded-tl-md px-5 py-4 shadow-lg shadow-black/10">
        <div className="flex gap-1.5">
          <span className="typing-dot w-2 h-2 rounded-full bg-accent-hover" />
          <span className="typing-dot w-2 h-2 rounded-full bg-accent-hover" />
          <span className="typing-dot w-2 h-2 rounded-full bg-accent-hover" />
        </div>
      </div>
    </motion.div>
  );
}

function ProductCards({
  products,
  logoUrl,
  onToggleProduct,
  onOpenMockup,
  isProductSelected,
}: {
  products: BrandKitProduct[];
  logoUrl: string | null;
  onToggleProduct: (p: BrandKitProduct) => void;
  onOpenMockup: (p: BrandKitProduct) => void;
  isProductSelected: (id: string) => boolean;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {products.map((product) => {
        const selected = isProductSelected(product.id);
        return (
          <div
            key={product.id}
            className={cn(
              "bg-dark-600/50 border rounded-xl overflow-hidden transition-all group",
              selected
                ? "border-accent/50 ring-1 ring-accent/20"
                : "border-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.12)]",
            )}
          >
            {/* Image */}
            <div className="relative aspect-[4/3] bg-dark-700/50 overflow-hidden">
              {product.image_url ? (
                <img
                  src={product.image_url}
                  alt={product.name}
                  loading="lazy"
                  className="w-full h-full object-contain p-2"
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <Package className="w-8 h-8 text-dark-300" />
                </div>
              )}

              {/* Selected badge */}
              {selected && (
                <div className="absolute top-2 right-2 w-5 h-5 bg-accent rounded-full flex items-center justify-center">
                  <Check className="w-3 h-3 text-white" />
                </div>
              )}

              {/* Hover actions */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 flex items-end justify-center pb-2 gap-1.5 opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={() => onToggleProduct(product)}
                  className={cn(
                    "flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg shadow-md transition-colors",
                    selected
                      ? "bg-red-500 text-white hover:bg-red-600"
                      : "bg-accent text-white hover:bg-accent-hover",
                  )}
                >
                  {selected ? <Check className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
                  {selected ? "Selectat" : "Selectează"}
                </button>
                {logoUrl && (
                  <button
                    onClick={() => onOpenMockup(product)}
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-dark-600 text-dark-100 text-[11px] font-medium rounded-lg shadow-md border border-[rgba(255,255,255,0.1)] hover:bg-dark-500 transition-colors"
                  >
                    <Eye className="w-3 h-3" />
                    Mockup
                  </button>
                )}
              </div>
            </div>

            {/* Info */}
            <div className="p-2.5">
              <p className="text-[11px] text-dark-300 mb-0.5">{product.supplier}</p>
              <h4 className="text-xs font-medium text-dark-100 line-clamp-2 min-h-[2rem]">
                {product.name}
              </h4>
              {product.print_areas.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {product.print_areas.slice(0, 2).map((pa, i) => (
                    <span
                      key={i}
                      className="text-[9px] px-1.5 py-0.5 bg-dark-500/50 text-dark-300 rounded"
                    >
                      {pa.location}
                      {pa.width_mm > 0 && ` ${pa.width_mm}×${pa.height_mm}mm`}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
