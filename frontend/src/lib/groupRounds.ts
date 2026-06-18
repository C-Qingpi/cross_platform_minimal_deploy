import type { Message } from "../types/api";

export interface ConversationRound {
  human: Message | null;
  activity: Message[];
  final: Message | null;
  /** Actual model from task_started event for this turn. */
  model?: string | null;
  /** Tail of a turn whose user message was evicted by summarization. */
  continuedFromCompaction?: boolean;
}

function lastAiIndex(msgs: Message[]): number | undefined {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].type === "ai") return i;
  }
  return undefined;
}

function isInProgressAi(msg: Message): boolean {
  if (msg.type !== "ai") return false;
  if (msg.tool_calls?.length) return true;
  const c = msg.content;
  return typeof c === "string" && c.startsWith("[Invoking");
}

function splitActivityFinal(
  rest: Message[],
  isLast: boolean,
  threadActive: boolean,
): Pick<ConversationRound, "activity" | "final"> {
  const aiIdx = lastAiIndex(rest);
  let final: Message | null = aiIdx !== undefined ? rest[aiIdx] : null;
  let activity = aiIdx !== undefined ? rest.filter((_, i) => i !== aiIdx) : [...rest];

  if (final && isLast && (threadActive || isInProgressAi(final))) {
    activity = [...activity, final];
    final = null;
  }

  return { activity, final };
}

/** Split checkpoint messages into user turns with activity vs final reply. */
export function groupIntoRounds(
  messages: Message[],
  threadActive = false,
): ConversationRound[] {
  const segments: Message[][] = [];
  const prefix: Message[] = [];
  let current: Message[] = [];

  for (const m of messages) {
    if (m.type === "human") {
      if (current.length) segments.push(current);
      current = [m];
    } else if (m.type !== "system") {
      if (current.length) {
        current.push(m);
      } else {
        prefix.push(m);
      }
    }
  }
  if (current.length) segments.push(current);

  const rounds: ConversationRound[] = [];

  if (prefix.length) {
    const { activity, final } = splitActivityFinal(
      prefix,
      segments.length === 0,
      threadActive,
    );
    rounds.push({
      human: null,
      activity,
      final,
      continuedFromCompaction: true,
    });
  }

  segments.forEach((seg, segIdx) => {
    const human = seg[0];
    const rest = seg.slice(1);
    const isLast = segIdx === segments.length - 1;
    const { activity, final } = splitActivityFinal(rest, isLast, threadActive);
    rounds.push({ human, activity, final });
  });

  return rounds;
}

export function messageReactKey(msg: Message, index: number): string {
  const id = msg.id ?? `idx-${index}`;
  const tools = msg.tool_calls?.map((t) => t.name).join(",") ?? "";
  return `${msg.type}:${id}:${tools}`;
}

/** Includes content length — for dedupe / change detection only, not React keys. */
export function messageDedupeKey(msg: Message, index: number): string {
  const content =
    typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content);
  const tools = msg.tool_calls?.map((t) => t.name).join(",") ?? "";
  return `${messageReactKey(msg, index)}:${content.length}:${tools}`;
}

/** Stable key for React lists — do not include content length. */
export function messageStableKey(msg: Message, index: number): string {
  return messageReactKey(msg, index);
}

export function roundStableKey(round: ConversationRound, index: number): string {
  if (round.human) return messageStableKey(round.human, index);
  const tail = round.final ?? round.activity[round.activity.length - 1];
  if (tail) return `continued:${messageStableKey(tail, index)}`;
  return `continued:${index}`;
}
