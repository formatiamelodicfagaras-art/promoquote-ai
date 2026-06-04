"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { Sparkles } from "lucide-react";
import { useStore } from "@/lib/store";
import MessageBubble, {
  TypingIndicator,
  StreamingBubble,
} from "./MessageBubble";

export default function MessageList() {
  const { messages, isAiTyping, streamingContent } = useStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAiTyping, streamingContent]);

  if (messages.length === 0 && !isAiTyping) {
    return <EmptyState />;
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-8 space-y-4 sm:space-y-6">
        <AnimatePresence mode="popLayout">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </AnimatePresence>

        {/* Streaming content */}
        {streamingContent && <StreamingBubble content={streamingContent} />}

        {/* Typing indicator (before streaming starts) */}
        <AnimatePresence>
          {isAiTyping && !streamingContent && <TypingIndicator />}
        </AnimatePresence>

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center max-w-md px-6">
        <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto mb-6 glow-accent">
          <Sparkles size={28} className="text-accent" />
        </div>
        <h2 className="text-xl font-semibold text-dark-50 mb-2">
          Bun venit la PromoQuote AI
        </h2>
        <p className="text-sm text-dark-200 leading-relaxed">
          Descrie ce produse promoționale cauți și voi genera o ofertă
          personalizată pentru tine. Poți cere cadouri, produse cu logo,
          articole pentru evenimente și multe altele.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {["Căni personalizate", "Tricouri cu logo", "Pixuri premium"].map(
            (example) => (
              <span
                key={example}
                className="px-3 py-1.5 rounded-full text-xs bg-dark-500/40 border border-[rgba(255,255,255,0.06)] text-dark-200"
              >
                {example}
              </span>
            )
          )}
        </div>
      </div>
    </div>
  );
}
