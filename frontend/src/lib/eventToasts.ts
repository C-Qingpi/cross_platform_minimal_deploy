import type { DeployEvent } from "../types/api";

/** Whether an event toast should display for the current agent/thread context. */
export function shouldShowEventToast(
  ev: DeployEvent,
  activeAgentId: string,
  activeThreadId: string,
): boolean {
  if (!ev.toast) return false;
  if (ev.agent_id && ev.agent_id !== activeAgentId) {
    if (ev.agent_id !== "unknown") return false;
    if (ev.thread && ev.thread !== activeThreadId) return false;
  }

  const thread = ev.thread;
  if (!thread) return true;

  const threadScoped = new Set([
    "summarizing",
    "summarizing_done",
    "task_error",
    "task_cancelled",
    "task_recursion_limit",
    "model_switched",
  ]);
  if (threadScoped.has(ev.event)) {
    return thread === activeThreadId;
  }
  return true;
}
