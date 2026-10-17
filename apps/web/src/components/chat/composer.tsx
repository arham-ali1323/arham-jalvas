"use client";

import { Send, Square } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Composer({
  onSend,
  onStop,
  busy,
  disabled,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");

  function submit() {
    const value = text.trim();
    if (!value || busy || disabled) return;
    setText("");
    onSend(value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="border-t border-border/60 bg-surface/50 p-4">
      <div className="flex items-end gap-3 rounded-xl border border-border bg-bg/60 p-2 focus-within:border-primary/50">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={disabled ? "Select or start a conversation…" : "Message MARK LIV…"}
          className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-slate-100 placeholder:text-muted focus:outline-none disabled:opacity-50"
        />
        {busy ? (
          <Button size="icon" variant="outline" onClick={onStop} aria-label="Stop">
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={submit}
            disabled={disabled || !text.trim()}
            aria-label="Send"
            className={cn(!text.trim() && "opacity-60")}
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-muted">
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}
