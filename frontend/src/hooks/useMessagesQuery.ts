import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AgentState, Message, MessagesResponse, StreamDraft } from "../types/api";
import * as api from "../lib/api";
import { mergeTailIntoWindow, DEFAULT_NUM_PAGES } from "../lib/mergeMessages";

const POLL_MS_IDLE = 1000;
const POLL_MS_ACTIVE = 200;

/**
 * React Query-powered hook — checkpoint-based pagination.
 *
 * - Default view: messages from 3 compression windows.
 * - Polls merge new messages into the current window.
 * - loadOlder loads the next older checkpoint window via before_checkpoint_id.
 * - discardOlder trims back to the latest 3 pages.
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

  const pageQuery = useQuery({
    queryKey,
    queryFn: () => api.fetchMessages(agentId, threadId, { numPages: DEFAULT_NUM_PAGES }),
    refetchInterval: () => {
      const state = queryClient.getQueryData<AgentState>(["agentState", agentId]);
      const active =
        state?.threads?.[threadId]?.active ||
        state?.active_threads?.includes(threadId);
      return active ? POLL_MS_ACTIVE : POLL_MS_IDLE;
    },
    staleTime: 0,
    enabled: Boolean(agentId) && Boolean(threadId),
  });

  // ── Sliding window display state ──────────────────────────────
  const [messages, setMessages] = useState<Message[]>([]);
  const [summary, setSummary] = useState("");
  const [streamDraft, setStreamDraft] = useState<StreamDraft | null>(null);
  const [turnModels, setTurnModels] = useState<string[]>([]);
  const [activeTurnModel, setActiveTurnModel] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);

  const beforeCheckpointRef = useRef<string | null>(null);
  const totalRef = useRef(0);
  const prevQueryRef = useRef<string>("");
  const messagesRef = useRef<Message[]>([]);

  messagesRef.current = messages;

  // ── Clear display on thread switch (before fetch completes) ───
  useEffect(() => {
    setMessages([]);
    setSummary("");
    setStreamDraft(null);
    setTurnModels([]);
    setActiveTurnModel(null);
    setHasOlder(false);
    beforeCheckpointRef.current = null;
    totalRef.current = 0;
    prevQueryRef.current = `${agentId}:${threadId}`;
  }, [agentId, threadId]);

  // ── Merge poll page into display ──────────────────────────────
  useEffect(() => {
    const page = pageQuery.data as MessagesResponse | undefined;
    if (!page) return;

    // Guard: discard data from a stale query (wrong thread)
    const firstMsg = page.messages[0];
    if (firstMsg && firstMsg.thread_id !== threadId) return;

    setSummary(page.summary);
    setStreamDraft(page.stream_draft ?? null);
    setTurnModels(page.turn_models ?? []);
    setActiveTurnModel(page.active_turn_model ?? null);

    // Thread switch? Reset everything.
    const currentKey = `${agentId}:${threadId}`;
    if (prevQueryRef.current !== currentKey) {
      prevQueryRef.current = currentKey;
      beforeCheckpointRef.current = page.before_checkpoint_id ?? null;
      totalRef.current = page.total;
      setMessages(page.messages);
      setHasOlder(page.has_older);
      return;
    }

    // User loaded older pages (messages > fresh tail)? Keep their view.
    // Otherwise (at tail), always merge fresh data — even when
    // before_checkpoint_id changes (new checkpoint after send).
    const loadedCount = messagesRef.current.length;
    if (loadedCount > page.messages.length) {
      totalRef.current = page.total;
      setHasOlder(page.has_older);
      return;
    }

    totalRef.current = page.total;
    setHasOlder(page.has_older);
    beforeCheckpointRef.current = page.before_checkpoint_id ?? null;

    setMessages((prev) =>
      mergeTailIntoWindow(prev, {
        messages: page.messages,
        start_index: page.start_index,
        total: page.total,
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageQuery.data, pageQuery.dataUpdatedAt]);

  // ── loadOlder — auto-triggered by scroll proximity ────────────
  const loadOlder = useCallback(async () => {
    if (!agentId || !threadId || loadingOlder) return;
    if (!hasOlder) return;
    setLoadingOlder(true);
    try {
      const cursor = beforeCheckpointRef.current;
      if (!cursor) return;
      const page = await api.fetchMessages(agentId, threadId, {
        beforeCheckpointId: cursor,
      });
      setMessages((prev) => [...page.messages, ...prev]);
      setTurnModels((prev) => [...(page.turn_models ?? []), ...prev]);
      setHasOlder(page.has_older);
      beforeCheckpointRef.current = page.before_checkpoint_id ?? null;
      totalRef.current = Math.max(totalRef.current, page.total);
    } finally {
      setLoadingOlder(false);
    }
  }, [agentId, threadId, loadingOlder, hasOlder]);

  // ── discardOlder — trim to default pages when at bottom ───────
  const discardOlder = useCallback(async () => {
    if (!hasOlder) return; // already at latest pages
    // Refetch fresh tail (3 pages) and replace
    const page = await api.fetchMessages(agentId, threadId, { numPages: DEFAULT_NUM_PAGES });
    setMessages(page.messages);
    setHasOlder(page.has_older);
    beforeCheckpointRef.current = page.before_checkpoint_id ?? null;
    totalRef.current = page.total;
    setTurnModels(page.turn_models ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, threadId, hasOlder]);

  // ── Manual refetch (after user sends a message) ───────────────
  const refreshTail = useCallback(async () => {
    const result = await pageQuery.refetch();
    return result.data;
  }, [pageQuery.refetch]);

  return {
    messages,
    summary,
    agentState,
    connected: pageQuery.isSuccess && agentQuery.isSuccess,
    total: totalRef.current || pageQuery.data?.total || 0,
    startIndex: 0,
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
