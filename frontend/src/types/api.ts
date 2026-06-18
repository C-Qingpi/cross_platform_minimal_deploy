export type MessageType = "human" | "ai" | "tool" | "system" | "error";

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  id?: string;
}

export interface ContentBlock {
  type: string;
  text?: string;
}

export interface Message {
  type: MessageType;
  id?: string;
  content: string | ContentBlock[];
  reasoning?: string;
  tool_calls?: ToolCall[];
  name?: string;
  tool_call_id?: string;
}

export interface ThreadInfo {
  thread_id: string;
  name: string;
  status?: string;
  active?: boolean;
  model?: string;
  wrapping_enabled?: boolean;
}

export interface AgentInfo {
  agent_id: string;
  workspace: string;
  model?: string;
  mounts: { name: string; path: string }[];
  state?: AgentState;
}

export interface AgentState {
  agent_id: string;
  status: string;
  model: string | null;
  active_threads?: string[];
  threads?: Record<string, {
    thread_id: string;
    status: string;
    active: boolean;
    finish_reason?: string;
    model?: string;
  }>;
}

export interface StreamDraft {
  content: string;
  reasoning: string;
  updated_at?: string;
}

export interface DeployEvent {
  index: number;
  event: string;
  ts: string;
  agent_id?: string;
  thread?: string;
  model?: string;
  error?: string;
  toast?: string;
  toast_ms?: number;
}

export interface EventsResponse {
  events: DeployEvent[];
  total: number;
  next_index: number;
}

export interface ToastState {
  message: string;
  ms: number;
}

export interface MessagesResponse {
  messages: Message[];
  summary: string;
  total: number;
  start_index: number;
  end_index: number;
  has_older: boolean;
  thread_state: Record<string, unknown>;
  queue: { id: string; content: string }[];
  stream_draft?: StreamDraft | null;
  /** Chronological actual models from task_started events (events.jsonl). */
  turn_models?: string[];
  task_models?: Record<string, string>;
  active_turn_model?: string | null;
}

export const CHAT_PAGE_SIZE = 500;
