import { useCallback, useEffect, useRef } from "react";

const PREFIX = "minimal-agent-draft";

function draftKey(agentId: string, threadId: string) {
  return `${PREFIX}:${agentId}:${threadId}`;
}

export function loadDraft(agentId: string, threadId: string): string {
  if (!agentId || !threadId) return "";
  return localStorage.getItem(draftKey(agentId, threadId)) ?? "";
}

export function useDraftStorage(
  agentId: string,
  threadId: string,
  draft: string,
  setDraft: (v: string) => void,
) {
  const prevThread = useRef({ agentId, threadId });

  useEffect(() => {
    if (!agentId || !threadId) return;
    if (
      prevThread.current.agentId !== agentId ||
      prevThread.current.threadId !== threadId
    ) {
      setDraft(loadDraft(agentId, threadId));
      prevThread.current = { agentId, threadId };
    }
  }, [agentId, threadId, setDraft]);

  useEffect(() => {
    if (!agentId || !threadId) return;
    const t = setTimeout(() => {
      const key = draftKey(agentId, threadId);
      if (draft.trim()) localStorage.setItem(key, draft);
      else localStorage.removeItem(key);
    }, 300);
    return () => clearTimeout(t);
  }, [agentId, threadId, draft]);

  const clearDraft = useCallback(() => {
    if (agentId && threadId) localStorage.removeItem(draftKey(agentId, threadId));
    setDraft("");
  }, [agentId, threadId, setDraft]);

  return { clearDraft };
}
