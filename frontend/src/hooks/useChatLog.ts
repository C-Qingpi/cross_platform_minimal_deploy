import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentState, Message, StreamDraft } from "../types/api";
import * as api from "../lib/api";
import { syncLiveTailPage, wasAtLiveTail } from "../lib/mergeMessages";

const POLL_MS_IDLE = 1000;
const POLL_MS_ACTIVE = 200;

export function useChatLog(agentId: string, threadId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [summary, setSummary] = useState("");
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [total, setTotal] = useState(0);
  const [startIndex, setStartIndex] = useState(0);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [connected, setConnected] = useState(false);
  const [streamDraft, setStreamDraft] = useState<StreamDraft | null>(null);
  const [turnModels, setTurnModels] = useState<string[]>([]);
  const [activeTurnModel, setActiveTurnModel] = useState<string | null>(null);

  const startIndexRef = useRef(0);
  const messagesLengthRef = useRef(0);
  const totalRef = useRef(0);
  const contextRef = useRef("");

  useEffect(() => {
    messagesLengthRef.current = messages.length;
  }, [messages.length]);

  const reset = useCallback(() => {
    setMessages([]);
    setSummary("");
    setTotal(0);
    setStartIndex(0);
    setHasOlder(false);
    setLoadingOlder(false);
    startIndexRef.current = 0;
    messagesLengthRef.current = 0;
    totalRef.current = 0;
    setStreamDraft(null);
    setTurnModels([]);
    setActiveTurnModel(null);
  }, []);

  const refreshTail = useCallback(async () => {
    if (!agentId || !threadId) return;

    const ctx = `${agentId}:${threadId}`;
    const contextChanged = contextRef.current !== ctx;

    const [page, state] = await Promise.all([
      api.fetchMessages(agentId, threadId),
      api.fetchAgentState(agentId),
    ]);
    setAgentState(state);
    setConnected(true);
    setSummary(page.summary);
    setStreamDraft(page.stream_draft ?? null);
    setTurnModels(page.turn_models ?? []);
    setActiveTurnModel(page.active_turn_model ?? null);

    if (contextChanged) {
      contextRef.current = ctx;
      setMessages(page.messages);
      setTotal(page.total);
      setHasOlder(page.has_older);
      setStartIndex(page.start_index);
      startIndexRef.current = page.start_index;
      totalRef.current = page.total;
      return;
    }

    const prevTotal = totalRef.current;
    const head = startIndexRef.current;
    const loadedCount = messagesLengthRef.current;
    const atLiveTail = wasAtLiveTail(head, loadedCount, prevTotal);

    totalRef.current = page.total;
    setTotal(page.total);
    setHasOlder(page.has_older || head > 0);

    if (loadedCount === 0) {
      setMessages(page.messages);
      setStartIndex(page.start_index);
      startIndexRef.current = page.start_index;
      return;
    }

    if (atLiveTail) {
      setMessages((prev) => syncLiveTailPage(prev, head, page));
      if (head > page.start_index) {
        setStartIndex(page.start_index);
        startIndexRef.current = page.start_index;
      }
    }
  }, [agentId, threadId]);

  const loadOlder = useCallback(async () => {
    if (!agentId || !threadId || loadingOlder || !hasOlder || startIndexRef.current === 0) {
      return;
    }
    setLoadingOlder(true);
    try {
      const page = await api.fetchMessages(agentId, threadId, {
        beforeIndex: startIndexRef.current,
      });
      setMessages((prev) => [...page.messages, ...prev]);
      setTurnModels((prev) => [...(page.turn_models ?? []), ...prev]);
      setStartIndex(page.start_index);
      setHasOlder(page.has_older);
      startIndexRef.current = page.start_index;
      totalRef.current = page.total;
      setTotal(page.total);
    } finally {
      setLoadingOlder(false);
    }
  }, [agentId, threadId, hasOlder, loadingOlder]);

  useEffect(() => {
    contextRef.current = "";
    reset();
  }, [agentId, threadId, reset]);

  const threadActive =
    Boolean(agentState?.threads?.[threadId]?.active) ||
    Boolean(agentState?.active_threads?.includes(threadId));

  const pollMs = threadActive || streamDraft ? POLL_MS_ACTIVE : POLL_MS_IDLE;

  useEffect(() => {
    refreshTail();
    const id = setInterval(refreshTail, pollMs);
    return () => clearInterval(id);
  }, [refreshTail, pollMs]);

  return {
    messages,
    summary,
    agentState,
    connected,
    total,
    startIndex,
    hasOlder,
    loadingOlder,
    loadOlder,
    refreshTail,
    streamDraft,
    turnModels,
    activeTurnModel,
  };
}
