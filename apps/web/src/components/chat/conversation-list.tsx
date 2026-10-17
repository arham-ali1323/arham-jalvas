"use client";

import { MessageSquare, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn, formatDate } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

export function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-border/60 bg-surface/30">
      <div className="border-b border-border/60 px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted">
        History
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted">
            No conversations yet.
          </p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <div
                  className={cn(
                    "group flex items-center gap-2 rounded-lg border border-transparent px-3 py-2 text-sm transition-colors",
                    activeId === conversation.id
                      ? "border-primary/40 bg-primary/10 text-primary-soft"
                      : "text-slate-300 hover:bg-surface-2 hover:text-white",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <MessageSquare className="h-4 w-4 shrink-0 opacity-70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{conversation.title}</span>
                      <span className="block truncate text-xs text-muted">
                        {formatDate(conversation.updated_at)}
                      </span>
                    </span>
                  </button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                    aria-label="Delete conversation"
                    onClick={() => onDelete(conversation.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-danger" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
