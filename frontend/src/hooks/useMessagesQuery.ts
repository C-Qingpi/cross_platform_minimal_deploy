import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AgentState, Message, MessagesResponse, StreamDraft } from "../types/api";
import * as api from "../lib/api";
import { syncLiveTailPage, wasAtLiveTail } from "../lib/mergeMessages";

const POLL_MS_IDLE = 1000;
const POLL_MS_ACTIVE = 200;
const TAIL_LIMIT = 20;

/**
 * React Query-powered hook — sliding window over message history.
 *
 * - React Query caches each fetched page by key (agent, thread, offset).
 * - A single `messages` state holds the visible window.
 * - Polls merge into the tail; `loadOlder` prepends older pages.
 * - `discardOlder` (called when user scrolls to bottom) trims back
 *   to TAIL_LIMIT to keep the virtual list small.
 */
export function useMessagesQuery(agentId: string, threadId: string) {
  const queryClient = useQueryClient();

  // ── Agent state ───────────────────────────────────────────────
  const agentQuery = useQuery({
    queryKey: ["agentState", agentId],
    queryFn: () => api.fetchAgentState(agentId),
    refetchInterval: POLL_MS_IDLE,
    staleTime: 500,
    enabled: Boolean(agentId),
  });
  const agentState: AgentState | null = agentQuery.data ?? null;

  // ── Messages page (React Query lifecycle) ─────────────────────
  const queryKey = ["messages", agentId, threadId];
  const firstFetchRef = useRef(true);
  const lastFetchedKeyRef = useRef("");

  const pageQuery = useQuery({
    queryKey,
    queryFn: () => {
      const key = `${agentId}:${threadId}`;
      if (lastFetchedKeyRef.current !== key) {
        lastFetchedKeyRef.current = key;
        firstFetchRef.current = true;
      }
      const limit = firstFetchRef.current ? TAIL_LIMIT : undefined;
      firstFetchRef.current = false;
      return api.fetchMessages(agentId, threadId, limit ? { limit } : undefined);
    },
    refetchInterval: () => {
      const state = queryClient.getQueryData<AgentState>(["agentState", agentId]);
      const active =
        state?.threads?.[threadId]?.active ||
        state?.active_threads?.includes(threadId);
      return active ? POLL_MS_ACTIVE : POLL_MS_IDLE;
    },
    staleTime: 0,
    gcTime: Infinity,  // never garbage-collect — return to thread shows cached data instantly
    placeholderData: (prev) => prev,  // keep previous thread's data while new one loads
    enabled: Boolean(agentId) && Boolean(threadId),
  });

  // ── Sliding window display state ──────────────────────────────
  const [messages, setMessages] = useState<Message[]>([]);
  const [summary, setSummary] = useState("");
  const [streamDraft, setStreamDraft] = useState<StreamDraft | null>(null);
  const [turnModels, setTurnModels] = useState<string[]>([]);
  const [activeTurnModel, setActiveTurnModel] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);

  const displayFromRef = useRef(0); // first index visible in `messages`
  const totalRef = useRef(0);
  const prevQueryRef = useRef<string>("");
  const messagesRef = useRef<Message[]>([]);

  // Keep ref in sync — used inside effect to avoid stale closures
  messagesRef.current = messages;

  // ── Merge poll page into display ──────────────────────────────
  useEffect(() => {
    const page = pageQuery.data as MessagesResponse | undefined;
    if (!page) return;

    setSummary(page.summary);
    setStreamDraft(page.stream_draft ?? null);
    setTurnModels(page.turn_models ?? []);
    setActiveTurnModel(page.active_turn_model ?? null);

    // Thread switch? Reset everything.
    const currentKey = `${agentId}:${threadId}`;
    if (prevQueryRef.current !== currentKey) {
      prevQueryRef.current = currentKey;
      displayFromRef.current = page.start_index;
      totalRef.current = page.total;
      setMessages(page.messages);
      return;
    }

    // Has displayFrom moved past the page? (user loaded older pages)
    // In that case, the poll page doesn't contain our display window start.
    // Don't merge — let the poll update metadata only.
    if (displayFromRef.current < page.start_index) {
      totalRef.current = page.total;
      return;
    }

    totalRef.current = page.total;

    // Use ref to read latest messages (avoids stale closure from effect deps)
    const currentMessages = messagesRef.current;
    const head = Math.max(displayFromRef.current, page.start_index);

    if (wasAtLiveTail(head, currentMessages.length, page.total)) {
      setMessages((prev) =>
        syncLiveTailPage(prev, head, {
          messages: page.messages,
          start_index: page.start_index,
          total: page.total,
        }),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageQuery.data, pageQuery.dataUpdatedAt]);

  // ── loadOlder — auto-triggered by scroll proximity ────────────
  const loadOlder = useCallback(async () => {
    if (!agentId || !threadId || loadingOlder) return;
    if (displayFromRef.current === 0) return; // nothing older
    setLoadingOlder(true);
    try {
      const page = await api.fetchMessages(agentId, threadId, {
        beforeIndex: displayFromRef.current,
      });
      setMessages((prev) => [...page.messages, ...prev]);
      setTurnModels((prev) => [...(page.turn_models ?? []), ...prev]);
      displayFromRef.current = page.start_index;
      totalRef.current = page.total;
    } finally {
      setLoadingOlder(false);
    }
  }, [agentId, threadId, loadingOlder]);

  // ── discardOlder — trim to tail when at bottom ────────────────
  const discardOlder = useCallback(() => {
    if (!totalRef.current) return;
    const tailStart = Math.max(0, totalRef.current - TAIL_LIMIT);
    if (displayFromRef.current >= tailStart) return; // already at tail

    // Discard: keep only the latest TAIL_LIMIT messages
    setMessages((prev) => prev.slice(-TAIL_LIMIT));
    displayFromRef.current = tailStart;
  }, []);

  // ── Manual refetch (after user sends a message) ───────────────
  const refreshTail = useCallback(async () => {
    const result = await pageQuery.refetch();
    return result.data;
  }, [pageQuery.refetch]);

  const hasOlder = displayFromRef.current > 0;

  return {
    messages,
    summary,
    agentState,
    connected: pageQuery.isSuccess && agentQuery.isSuccess,
    total: totalRef.current || pageQuery.data?.total || 0,
    startIndex: displayFromRef.current,
    hasOlder,
    loadingOlder,
    loadOlder,
    discardOlder,
    refreshTail,
    streamDraft,
    turnModels,
    activeTurnModel,
  };
}
