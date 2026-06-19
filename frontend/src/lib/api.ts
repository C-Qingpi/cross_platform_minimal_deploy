import type { EventsResponse, MessagesResponse } from "../types/api";
import { CHAT_PAGE_SIZE } from "../types/api";

const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
};

/** Parse a fetch response, throwing a descriptive error on non-OK status. */
async function safeJson<T = unknown>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail: string = body?.detail ?? fallback;
    throw new Error(detail);
  }
  return res.json();
}

export interface FsRoot {
  name: string;
  path: string;
}

export interface FsEntry {
  name: string;
  path: string;
  has_children: boolean;
}

export interface FsBrowseResult {
  path: string;
  parent: string | null;
  entries: FsEntry[];
}

export async function fetchFsRoots(): Promise<FsRoot[]> {
  const res = await fetch("/api/fs/roots");
  return safeJson(res, "Failed to load filesystem roots");
}

export async function browseDirectory(path: string): Promise<FsBrowseResult> {
  const res = await fetch(`/api/fs/browse${qs({ path })}`);
  return safeJson(res, "Failed to browse directory");
}

export async function fetchDefaultWorkspace(agentId: string): Promise<string> {
  const res = await fetch(`/api/fs/default-workspace${qs({ agent_id: agentId })}`);
  const data = await safeJson<{ path: string }>(res, "Failed to load default workspace");
  return data.path;
}

export async function fetchAgents() {
  const res = await fetch("/api/agents");
  return safeJson(res, "Failed to load agents");
}

export async function createAgent(body: {
  agent_id: string;
  workspace?: string;
  model?: string;
  mounts?: { name: string; path: string }[];
}) {
  const res = await fetch("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return safeJson(res, "Failed to create agent");
}

export async function deleteAgent(agentId: string) {
  const res = await fetch(`/api/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
  return safeJson(res, "Failed to delete agent");
}

export async function fetchAgentState(agentId: string) {
  const res = await fetch(`/api/agent/state${qs({ agent_id: agentId })}`);
  return safeJson(res, "Failed to load agent state");
}

export async function fetchMessages(
  agentId: string,
  threadId: string,
  options?: { limit?: number; beforeIndex?: number },
): Promise<MessagesResponse> {
  const params: Record<string, string | undefined> = {
    agent_id: agentId,
    thread_id: threadId,
    limit: String(options?.limit ?? CHAT_PAGE_SIZE),
  };
  if (options?.beforeIndex !== undefined) {
    params.before_index = String(options.beforeIndex);
  }
  const res = await fetch(`/api/messages${qs(params)}`);
  return safeJson(res, "Failed to load messages");
}

export async function sendMessage(agentId: string, threadId: string, content: string) {
  const res = await fetch(`/api/messages${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, thread_id: threadId }),
  });
  return safeJson(res, "Failed to send message");
}

export async function stopChat(agentId: string, threadId: string) {
  const res = await fetch(`/api/agent/stop${qs({ agent_id: agentId, thread_id: threadId })}`, { method: "POST" });
  return safeJson(res, "Stop request failed");
}

export async function switchModel(agentId: string, model: string, threadId?: string) {
  const res = await fetch(`/api/agent/model${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, thread_id: threadId }),
  });
  return safeJson(res, "Failed to switch model");
}

export async function fetchThreads(agentId: string) {
  const res = await fetch(`/api/threads${qs({ agent_id: agentId })}`);
  return safeJson(res, "Failed to load threads");
}

export async function createThread(agentId: string, threadId: string, name?: string) {
  const res = await fetch(`/api/threads${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, name }),
  });
  return safeJson(res, "Failed to create thread");
}

export async function deleteThread(agentId: string, threadId: string) {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}${qs({ agent_id: agentId })}`, {
    method: "DELETE",
  });
  return safeJson(res, "Failed to delete thread");
}

export async function fetchEvents(afterIndex = 0, agentId?: string): Promise<EventsResponse> {
  const params: Record<string, string | undefined> = {
    after_index: String(afterIndex),
  };
  if (agentId) params.agent_id = agentId;
  const res = await fetch(`/api/events${qs(params)}`);
  return safeJson(res, "Failed to load events");
}

export async function setThreadWrapping(agentId: string, threadId: string, enabled: boolean) {
  const res = await fetch(`/api/thread/wrapping${qs({ agent_id: agentId, thread_id: threadId, enabled: String(enabled) })}`, {
    method: "POST",
  });
  return safeJson(res, "Failed to set thread wrapping");
}

export async function fetchConfig() {
  const res = await fetch("/api/config");
  return safeJson(res, "Failed to load config");
}
