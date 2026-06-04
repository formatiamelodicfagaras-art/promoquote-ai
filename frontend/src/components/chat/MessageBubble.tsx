"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Message } from "@/types";
import ProductCards from "./ProductCards";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  const timeString = new Date(message.timestamp).toLocaleTimeString("ro-RO", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={cn("flex gap-3 group", isUser ? "flex-row-reverse" : "")}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center mt-1",
          isUser
            ? "bg-accent text-white"
            : "bg-dark-500 border border-[rgba(255,255,255,0.08)] text-accent-hover"
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* Bubble */}
      <div className={cn("max-w-[90%] sm:max-w-[75%] space-y-2", isUser ? "items-end" : "")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-[14px] leading-relaxed",
            isUser
              ? "bg-accent text-white rounded-tr-md"
              : "bg-dark-500 border border-[rgba(255,255,255,0.06)] text-dark-50 rounded-tl-md shadow-lg shadow-black/10"
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

        {/* Product cards inline */}
        {message.products && message.products.length > 0 && (
          <ProductCards products={message.products} />
        )}

        {/* Timestamp */}
        <p
          className={cn(
            "text-[11px] text-dark-200 opacity-0 group-hover:opacity-100 transition-opacity px-1",
            isUser ? "text-right" : ""
          )}
        >
          {timeString}
        </p>
      </div>
    </motion.div>
  );
}

export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex gap-3"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-dark-500 border border-[rgba(255,255,255,0.08)] text-accent-hover">
        <Bot size={16} />
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

export function StreamingBubble({ content }: { content: string }) {
  if (!content) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-dark-500 border border-[rgba(255,255,255,0.08)] text-accent-hover">
        <Bot size={16} />
      </div>
      <div className="max-w-[90%] sm:max-w-[75%] bg-dark-500 border border-[rgba(255,255,255,0.06)] rounded-2xl rounded-tl-md px-4 py-3 shadow-lg shadow-black/10">
        <div className="ai-markdown text-[14px] leading-relaxed text-dark-50">
          <ReactMarkdown>{content}</ReactMarkdown>
          <span className="inline-block w-2 h-4 bg-accent-hover/70 animate-pulse ml-0.5 -mb-0.5 rounded-sm" />
        </div>
      </div>
    </motion.div>
  );
}
