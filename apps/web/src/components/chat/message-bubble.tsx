"use client";

import { motion } from "framer-motion";
import { Sparkles, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";

export function MessageBubble({
  role,
  content,
  pending = false,
}: {
  role: string;
  content: string;
  pending?: boolean;
}) {
  const isUser = role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <span
        className={cn(
          "mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg border",
          isUser
            ? "border-border bg-surface-2 text-slate-300"
            : "border-primary/40 bg-primary/10 text-primary shadow-glow-sm",
        )}
      >
        {isUser ? <UserRound className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
      </span>
      <div
        className={cn(
          "max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary/15 text-slate-100"
            : "border border-border/70 bg-surface/70 text-slate-100",
        )}
      >
        {content || (pending ? <TypingDots /> : null)}
      </div>
    </motion.div>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse-glow rounded-full bg-primary"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </span>
  );
}
