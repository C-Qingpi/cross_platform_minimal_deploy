import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentInfo, ThreadInfo } from "./types/api";
import { CreateAgentModal } from "./components/CreateAgentModal";
import { SidebarPanel } from "./components/SidebarPanel";
import { PaginatedConversationLog } from "./components/PaginatedConversationLog";
import { Toast } from "./components/Toast";
import { useEventToasts } from "./hooks/useEventToasts";
import { useDraftStorage } from "./hooks/useDraftStorage";
import { useChatLog } from "./hooks/useChatLog";
import { attachTurnModels } from "./lib/turnModels";
import { groupIntoRounds, messageStableKey } from "./lib/groupRounds";
import * as api from "./lib/api";

const MODELS = [
  "deepseek:deepseek_v4_flash",
  "deepseek:deepseek_v4_pro",
  "openai:gpt-4o-mini",
  "anthropic:claude-sonnet-4-5",
  "moonshot:kimi-k2.5",
];

const ACTIVE_AGENT_KEY = "minimal-agent-active-id";
const ACTIVE_THREAD_PREFIX = "minimal-agent-thread:";

type ExpandedPanel = "agents" | "threads" | null;

function finalKeyForRound(round: ReturnType<typeof groupIntoRounds>[number], index: number) {
  if (!round.final) return null;
  return messageStableKey(round.final, index * 1000 + 999);
}

export default function App() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [activeAgentId, setActiveAgentId] = useState(
    () => localStorage.getItem(ACTIVE_AGENT_KEY) || "default",
  );
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [draft, setDraft] = useState("");
  const [model, setModel] = useState("deepseek:deepseek_v4_flash");
  const [expandedPanel, setExpandedPanel] = useState<ExpandedPanel>(null);
  const [animateFinalKey, setAnimateFinalKey] = useState<string | null>(null);
  const [createAgentOpen, setCreateAgentOpen] = useState(false);
  const [scrollFollowReset, setScrollFollowReset] = useState(0);
  const [wrappingEnabled, setWrappingEnabled] = useState(true);
  const [menuOpenThreadId, setMenuOpenThreadId] = useState<string | null>(null);

  const knownFinalKeysRef = useRef<Set<string>>(new Set());
  const contextRef = useRef("");
  const pendingModelRef = useRef<string | null>(null);

  const mainThread = activeAgentId ? `${activeAgentId}-main` : "";
  const { clearDraft } = useDraftStorage(activeAgentId, activeThreadId, draft, setDraft);

  const {
    messages,
    summary,
    agentState,
    connected,
    total,
    hasOlder,
    loadingOlder,
    loadOlder,
    refreshTail,
    streamDraft,
    turnModels,
    activeTurnModel,
  } = useChatLog(activeAgentId, activeThreadId);

  const threadActive = Boolean(agentState?.threads?.[activeThreadId]?.active);
  const threadStatus = agentState?.threads?.[activeThreadId]?.status;
  const { toast, showToast } = useEventToasts(activeAgentId, activeThreadId, agentState);
  const rounds = useMemo(
    () => attachTurnModels(groupIntoRounds(messages), turnModels),
    [messages, turnModels],
  );

  const refreshAgents = useCallback(async () => {
    const data = await api.fetchAgents();
    setAgents(data);
    if (data.length && !data.find((a: AgentInfo) => a.agent_id === activeAgentId)) {
      setActiveAgentId(data[0].agent_id);
    }
  }, [activeAgentId]);

  const refreshThreads = useCallback(async () => {
    if (!activeAgentId) return;
    const data = await api.fetchThreads(activeAgentId);
    setThreads(data);
    const stored = localStorage.getItem(`${ACTIVE_THREAD_PREFIX}${activeAgentId}`);
    const preferred = stored && data.find((t: ThreadInfo) => t.thread_id === stored);
    if (preferred) {
      setActiveThreadId(stored!);
    } else if (!activeThreadId || !data.find((t: ThreadInfo) => t.thread_id === activeThreadId)) {
      setActiveThreadId(data[0]?.thread_id || mainThread);
    }
  }, [activeAgentId, activeThreadId, mainThread]);

  useEffect(() => {
    refreshAgents();
  }, [refreshAgents]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_AGENT_KEY, activeAgentId);
    refreshThreads();
  }, [activeAgentId, refreshThreads]);

  useEffect(() => {
    if (activeAgentId && activeThreadId) {
      localStorage.setItem(`${ACTIVE_THREAD_PREFIX}${activeAgentId}`, activeThreadId);
    }
  }, [activeAgentId, activeThreadId]);

  // Close thread dropdown when clicking outside
  useEffect(() => {
    if (!menuOpenThreadId) return;
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('[data-thread-menu]')) {
        setMenuOpenThreadId(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpenThreadId]);

  useEffect(() => {
    if (pendingModelRef.current) {
      setModel(pendingModelRef.current);
      return;
    }
    const thread = threads.find((t) => t.thread_id === activeThreadId);
    if (thread?.model) {
      setModel(thread.model);
      return;
    }
    const stateModel = agentState?.threads?.[activeThreadId]?.model;
    if (stateModel) {
      setModel(stateModel);
      return;
    }
    if (agentState?.model) {
      setModel(agentState.model);
    }
  }, [threads, activeThreadId, agentState]);

  useEffect(() => {
    const ctx = `${activeAgentId}:${activeThreadId}`;
    if (contextRef.current !== ctx) {
      contextRef.current = ctx;
      knownFinalKeysRef.current = new Set();
      setAnimateFinalKey(null);
      // Reset wrapping to threads.json value on thread switch
      const t = threads.find((th) => th.thread_id === activeThreadId);
      if (t?.wrapping_enabled !== undefined) {
        setWrappingEnabled(t.wrapping_enabled);
      }
    }
    const rs = groupIntoRounds(messages);
    const keys = rs.map((r, i) => finalKeyForRound(r, i)).filter(Boolean) as string[];

    if (knownFinalKeysRef.current.size === 0 && keys.length) {
      keys.forEach((k) => knownFinalKeysRef.current.add(k));
      return;
    }

    const newest = keys[keys.length - 1];
    if (newest && !knownFinalKeysRef.current.has(newest)) {
      knownFinalKeysRef.current.add(newest);
      setAnimateFinalKey(newest);
    }
  }, [messages, activeAgentId, activeThreadId, agentState]);

  const agentOnline = agentState?.status === "online";

  const handleSend = async () => {
    if (!draft.trim()) return;
    const content = draft.trim();
    clearDraft();
    setScrollFollowReset((k) => k + 1);
    await api.sendMessage(activeAgentId, activeThreadId, content);
    refreshTail();
  };

  const handleStop = async () => {
    if (!agentOnline) {
      showToast("Agent runner offline — start agent_runner.py");
      return;
    }
    if (!threadActive) {
      showToast("Nothing running on this thread");
      return;
    }
    showToast("Sending stop…", 2000);
    try {
      await api.stopChat(activeAgentId, activeThreadId);
      await refreshTail();
    } catch {
      showToast("Stop request failed");
    }
  };

  const handleModelChange = async (next: string) => {
    pendingModelRef.current = next;
    setModel(next);
    await api.switchModel(activeAgentId, next, activeThreadId);
    await refreshThreads();
    pendingModelRef.current = null;
    refreshTail();
  };

  const handleWrappingToggle = async () => {
    const next = !wrappingEnabled;
    setWrappingEnabled(next);
    await api.setThreadWrapping(activeAgentId, activeThreadId, next);
  };

  const handleCreateAgent = () => {
    setCreateAgentOpen(true);
  };

  const handleAgentCreated = async (agentId: string) => {
    await refreshAgents();
    setActiveAgentId(agentId);
  };

  const handleDeleteAgent = async () => {
    if (!confirm(`Delete agent ${activeAgentId}?`)) return;
    await api.deleteAgent(activeAgentId);
    await refreshAgents();
  };

  const handleCreateThread = async () => {
    const id = prompt("Thread id:");
    if (!id?.trim()) return;
    await api.createThread(activeAgentId, id.trim());
    await refreshThreads();
    setActiveThreadId(id.trim());
  };

  const handleDeleteThread = async (threadId: string) => {
    if (threadId === mainThread) {
      alert("Cannot delete main thread");
      return;
    }
    if (!confirm(`Delete thread ${threadId}?`)) return;
    await api.deleteThread(activeAgentId, threadId);
    await refreshThreads();
  };

  const handleBranchThread = async (threadId: string) => {
    try {
      const result = await api.branchThread(activeAgentId, threadId);
      await refreshThreads();
      setActiveThreadId(result.thread_id);
    } catch (e) {
      alert("Branch failed: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleRenameThread = async (threadId: string) => {
    const currentName = threads.find((t) => t.thread_id === threadId)?.name || threadId;
    const name = prompt("New thread name:", currentName);
    if (!name?.trim()) return;
    try {
      await api.renameThread(activeAgentId, threadId, name.trim());
      await refreshThreads();
    } catch (e) {
      alert("Rename failed: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleResetSearchIndex = async () => {
    if (
      !confirm(
        "Clear the semantic search index for this agent's workspace?\n\n"
        + "The index will rebuild in the background. Search may return no results until indexing catches up.",
      )
    ) {
      return;
    }
    showToast("Resetting search index…", 2000);
    try {
      const result = await api.resetSearchIndex(activeAgentId);
      showToast(result.message, 4000);
    } catch {
      showToast("Failed to reset search index");
    }
  };

  const togglePanel = (panel: ExpandedPanel) => {
    setExpandedPanel((cur) => (cur === panel ? null : panel));
  };

  const agentsCollapsed = expandedPanel === "threads";
  const threadsCollapsed = expandedPanel === "agents";

  return (
    <div className="flex h-screen overflow-hidden">
      <CreateAgentModal
        open={createAgentOpen}
        onClose={() => setCreateAgentOpen(false)}
        onCreated={handleAgentCreated}
      />
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white flex flex-col min-h-0">
        <SidebarPanel
          title="Agents"
          expanded={expandedPanel === "agents"}
          onToggleExpand={() => togglePanel("agents")}
          collapsed={agentsCollapsed}
          actions={
            <>
              <button type="button" onClick={handleCreateAgent} className="rounded-md bg-indigo-600 px-2 py-0.5 text-xs text-white">+</button>
              <button type="button" onClick={handleDeleteAgent} className="rounded-md border border-slate-300 px-2 py-0.5 text-xs">Del</button>
            </>
          }
        >
          <div className="space-y-1">
            {agents.map((a) => (
              <button
                key={a.agent_id}
                type="button"
                onClick={() => setActiveAgentId(a.agent_id)}
                className={`w-full rounded-lg px-2 py-2 text-left text-sm ${
                  a.agent_id === activeAgentId ? "bg-indigo-50 text-indigo-700" : "hover:bg-slate-50"
                }`}
              >
                <div className="font-medium">{a.agent_id}</div>
                <div className="text-xs text-slate-500 truncate">{a.state?.status || "offline"}</div>
                {a.workspace && expandedPanel === "agents" && (
                  <div className="text-[10px] text-slate-400 mt-1 break-all leading-tight">{a.workspace}</div>
                )}
              </button>
            ))}
          </div>
        </SidebarPanel>

        <SidebarPanel
          title="Threads"
          expanded={expandedPanel === "threads"}
          onToggleExpand={() => togglePanel("threads")}
          collapsed={threadsCollapsed}
          actions={
            <button type="button" onClick={handleCreateThread} className="rounded-md border border-slate-300 px-2 py-0.5 text-xs">+</button>
          }
        >
          <div className="space-y-1">
            {threads.map((t) => (
              <div key={t.thread_id} className="group relative flex items-center rounded px-1 py-1 has-[[data-thread-menu]]:bg-slate-50">
                <button
                  type="button"
                  onClick={() => setActiveThreadId(t.thread_id)}
                  className={`flex-1 rounded px-1.5 py-1 text-left text-xs ${
                    t.thread_id === activeThreadId ? "bg-slate-100 font-medium" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="truncate">{t.name || t.thread_id}</span>
                    {t.active && <span className="text-[10px] text-amber-600 shrink-0">●</span>}
                  </div>
                  {expandedPanel === "threads" && (
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">{t.thread_id}</div>
                  )}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpenThreadId(menuOpenThreadId === t.thread_id ? null : t.thread_id);
                  }}
                  className="shrink-0 rounded px-1 py-1 text-xs text-slate-400 hover:text-slate-700 hover:bg-slate-200 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Thread actions"
                >
                  ⋮
                </button>
                {menuOpenThreadId === t.thread_id && (
                  <div
                    data-thread-menu="true"
                    className="absolute right-0 top-full z-50 mt-0.5 w-32 rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
                  >
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRenameThread(t.thread_id).finally(() => setMenuOpenThreadId(null));
                      }}
                      className="w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      ✏️ Rename
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBranchThread(t.thread_id).finally(() => setMenuOpenThreadId(null));
                      }}
                      className="w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      🌿 Branch
                    </button>
                    <hr className="my-1 border-slate-100" />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteThread(t.thread_id).finally(() => setMenuOpenThreadId(null));
                      }}
                      className="w-full px-3 py-1.5 text-left text-xs text-red-600 hover:bg-red-50"
                    >
                      🗑 Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </SidebarPanel>
      </aside>

      <div className="flex flex-1 flex-col min-w-0 min-h-0 overflow-hidden">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2 shrink-0">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${connected && agentOnline ? "bg-emerald-500" : "bg-slate-300"}`} />
            <span className="text-sm font-medium">{activeAgentId}</span>
            <span className="text-xs text-slate-500">{activeThreadId}</span>
            {total > 0 && (
              <span className="text-xs text-slate-400">{total.toLocaleString()} msgs</span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <label className="text-xs text-slate-500">Model</label>
            <select
              value={model}
              onChange={(e) => handleModelChange(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-sm"
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            {threadActive && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                {threadStatus === "summarizing" ? "summarizing" : "running"}
              </span>
            )}
            <label className="flex items-center gap-1.5 cursor-pointer select-none" title={wrappingEnabled ? "User messages are wrapped (RECEIVED FROM USER: ...)" : "User messages sent raw, no wrapping"}>
              <span className="text-xs text-slate-500">Wrap</span>
              <button
                type="button"
                role="switch"
                aria-checked={wrappingEnabled}
                onClick={handleWrappingToggle}
                className={`relative inline-flex h-4 w-7 shrink-0 rounded-full border transition-colors ${
                  wrappingEnabled ? "bg-indigo-500 border-indigo-500" : "bg-slate-200 border-slate-300"
                }`}
              >
                <span
                  className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${
                    wrappingEnabled ? "translate-x-3.5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </label>
            <button
              type="button"
              onClick={handleResetSearchIndex}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
              title="Clear semantic search index and rebuild from workspace"
            >
              Reset index
            </button>
          </div>
        </header>

        <PaginatedConversationLog
          rounds={rounds}
          summary={summary}
          animateFinalKey={animateFinalKey}
          hasOlder={hasOlder}
          loadingOlder={loadingOlder}
          total={total}
          loadedCount={messages.length}
          threadActive={threadActive}
          streamDraft={streamDraft}
          activeTurnModel={activeTurnModel}
          followResetKey={scrollFollowReset}
          onLoadOlder={loadOlder}
        />

        <footer className="relative z-20 shrink-0 border-t border-slate-200 bg-white px-4 py-3">
          <div className="mx-auto flex w-full max-w-3xl gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={2}
              placeholder="Message agent…"
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={handleSend}
                disabled={!draft.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40"
              >
                Send
              </button>
              <button
                type="button"
                onClick={handleStop}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                Stop
              </button>
            </div>
          </div>
        </footer>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
