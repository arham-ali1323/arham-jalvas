"use client";

import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAppState } from "@/components/app-state-provider";
import { Composer } from "@/components/chat/composer";
import { ConversationList } from "@/components/chat/conversation-list";
import { MessageBubble } from "@/components/chat/message-bubble";
import { chat, conversations as conversationsApi } from "@/lib/api";
import type { Conversation, Message } from "@/lib/types";

type LocalMessage = Message & { pending?: boolean };

let tempCounter = 0;
const tempId = () => `local-${++tempCounter}`;

export default function ChatPage() {
  const { activeConversationId, setActiveConversationId } = useAppState();

  const [items, setItems] = useState<Conversation[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      setItems(await conversationsApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations.");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoadingThread(true);
    conversationsApi
      .get(activeConversationId)
      .then((detail) => {
        if (!cancelled) setMessages(detail.messages);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load conversation.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingThread(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeConversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = useCallback(
    (text: string) => {
      setError(null);
      setBusy(true);

      const userMessage: LocalMessage = {
        id: tempId(),
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };
      const assistantMessage: LocalMessage = {
        id: tempId(),
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        pending: true,
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      const controller = new AbortController();
      abortRef.current = controller;
      let resolvedId: string | null = activeConversationId;

      void chat
        .stream(
          { message: text, conversation_id: activeConversationId },
          {
            onDelta: (chunk) =>
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMessage.id
                    ? { ...m, content: m.content + chunk, pending: false }
                    : m,
                ),
              ),
            onConversation: (id) => {
              resolvedId = id;
              if (id !== activeConversationId) setActiveConversationId(id);
            },
            onError: (message) => setError(message),
          },
          controller.signal,
        )
        .finally(async () => {
          setBusy(false);
          abortRef.current = null;
          if (resolvedId) {
            try {
              const detail = await conversationsApi.get(resolvedId);
              setMessages(detail.messages);
            } catch {
              /* keep optimistic transcript */
            }
          }
          void loadList();
        });
    },
    [activeConversationId, loadList, setActiveConversationId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
  }, []);

  const remove = useCallback(
    async (id: string) => {
      try {
        await conversationsApi.remove(id);
        if (id === activeConversationId) setActiveConversationId(null);
        await loadList();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete.");
      }
    },
    [activeConversationId, loadList, setActiveConversationId],
  );

  const activeTitle =
    items.find((c) => c.id === activeConversationId)?.title ?? "New conversation";

  return (
    <div className="flex h-full">
      <ConversationList
        conversations={items}
        activeId={activeConversationId}
        loading={loadingList}
        onSelect={setActiveConversationId}
        onDelete={(id) => void remove(id)}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center border-b border-border/60 px-6">
          <h1 className="truncate text-sm font-medium text-slate-200">{activeTitle}</h1>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto p-6">
          {loadingThread ? null : messages.length === 0 ? (
            <Welcome />
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                role={message.role}
                content={message.content}
                pending={message.pending}
              />
            ))
          )}
        </div>

        {error ? <p className="px-6 pb-1 text-sm text-danger">{error}</p> : null}

        <Composer onSend={send} onStop={stop} busy={busy} disabled={loadingThread} />
      </div>
    </div>
  );
}

function Welcome() {
  return (
    <div className="grid h-full place-items-center text-center">
      <div className="max-w-md">
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-primary/40 bg-primary/10 text-primary shadow-glow">
          <Sparkles className="h-5 w-5" />
        </span>
        <h2 className="mt-4 text-lg font-semibold text-white">How can I help today?</h2>
        <p className="mt-2 text-sm text-muted">
          Ask a question, draft something, or just say hello. Your conversations are saved to
          your account.
        </p>
      </div>
    </div>
  );
}
