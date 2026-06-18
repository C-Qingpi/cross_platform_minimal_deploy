const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
};

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
  if (!res.ok) throw new Error("Failed to load filesystem roots");
  return res.json();
}

export async function browseDirectory(path: string): Promise<FsBrowseResult> {
  const res = await fetch(`/api/fs/browse${qs({ path })}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to browse directory");
  }
  return res.json();
}

export async function fetchDefaultWorkspace(agentId: string): Promise<string> {
  const res = await fetch(`/api/fs/default-workspace${qs({ agent_id: agentId })}`);
  const data = await res.json();
  return data.path;
}

export async function fetchAgents() {
  const res = await fetch("/api/agents");
  return res.json();
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
  return res.json();
}

export async function deleteAgent(agentId: string) {
  const res = await fetch(`/api/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
  return res.json();
}

export async function fetchAgentState(agentId: string) {
  const res = await fetch(`/api/agent/state${qs({ agent_id: agentId })}`);
  return res.json();
}

import type { EventsResponse, MessagesResponse } from "../types/api";
import { CHAT_PAGE_SIZE } from "../types/api";

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
  return res.json();
}

export async function sendMessage(agentId: string, threadId: string, content: string) {
  const res = await fetch(`/api/messages${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, thread_id: threadId }),
  });
  return res.json();
}

export async function stopChat(agentId: string, threadId: string) {
  const res = await fetch(`/api/agent/stop${qs({ agent_id: agentId, thread_id: threadId })}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Stop request failed");
  }
  return res.json();
}

export async function switchModel(agentId: string, model: string, threadId?: string) {
  const res = await fetch(`/api/agent/model${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, thread_id: threadId }),
  });
  return res.json();
}

export async function fetchThreads(agentId: string) {
  const res = await fetch(`/api/threads${qs({ agent_id: agentId })}`);
  return res.json();
}

export async function createThread(agentId: string, threadId: string, name?: string) {
  const res = await fetch(`/api/threads${qs({ agent_id: agentId })}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, name }),
  });
  return res.json();
}

export async function deleteThread(agentId: string, threadId: string) {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}${qs({ agent_id: agentId })}`, {
    method: "DELETE",
  });
  return res.json();
}

export async function fetchEvents(afterIndex = 0, agentId?: string): Promise<EventsResponse> {
  const params: Record<string, string | undefined> = {
    after_index: String(afterIndex),
  };
  if (agentId) params.agent_id = agentId;
  const res = await fetch(`/api/events${qs(params)}`);
  return res.json();
}

export async function fetchConfig() {
  const res = await fetch("/api/config");
  return res.json();
}
