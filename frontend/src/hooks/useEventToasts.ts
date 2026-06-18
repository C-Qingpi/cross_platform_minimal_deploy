import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentState, ToastState } from "../types/api";
import * as api from "../lib/api";
import { shouldShowEventToast } from "../lib/eventToasts";

const POLL_MS_IDLE = 1000;
const POLL_MS_ACTIVE = 200;

export function useEventToasts(
  activeAgentId: string,
  activeThreadId: string,
  agentState: AgentState | null,
) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const lastIndexRef = useRef(0);
  const contextRef = useRef("");
  const summarizingRef = useRef(false);

  const showToast = useCallback((message: string, ms = 3500) => {
    setToast({ message, ms });
  }, []);

  const threadActive = Boolean(agentState?.threads?.[activeThreadId]?.active);
  const threadSummarizing = agentState?.threads?.[activeThreadId]?.status === "summarizing";
  const pollMs = threadActive || threadSummarizing ? POLL_MS_ACTIVE : POLL_MS_IDLE;

  useEffect(() => {
    const summarizing = threadSummarizing;
    if (summarizing && !summarizingRef.current) {
      showToast(`Summarizing conversation history… (${activeThreadId})`, 6000);
    }
    summarizingRef.current = summarizing;
  }, [threadSummarizing, activeThreadId, showToast]);

  useEffect(() => {
    if (!activeAgentId) return;

    const ctx = `${activeAgentId}:${activeThreadId}`;
    let cancelled = false;

    if (contextRef.current !== ctx) {
      contextRef.current = ctx;
      summarizingRef.current = threadSummarizing;
      api.fetchEvents(Number.MAX_SAFE_INTEGER, activeAgentId).then((page) => {
        if (!cancelled && contextRef.current === ctx) {
          lastIndexRef.current = page.total;
        }
      });
    }

    const poll = async () => {
      const page = await api.fetchEvents(lastIndexRef.current, activeAgentId);
      lastIndexRef.current = page.next_index;

      let nextToast: ToastState | null = null;
      for (const ev of page.events) {
        if (!shouldShowEventToast(ev, activeAgentId, activeThreadId)) continue;
        if (!ev.toast) continue;
        const ms = ev.toast_ms ?? 3500;
        if (ev.event === "summarizing") {
          nextToast = { message: ev.toast, ms };
          break;
        }
        nextToast = { message: ev.toast, ms };
      }
      if (nextToast) setToast(nextToast);
    };

    poll();
    const id = setInterval(poll, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeAgentId, activeThreadId, pollMs, threadSummarizing]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), toast.ms);
    return () => window.clearTimeout(id);
  }, [toast]);

  return { toast, showToast };
}
