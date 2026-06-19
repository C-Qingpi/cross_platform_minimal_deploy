import { memo, useRef, useState, type ReactNode } from "react";
import type { Message, StreamDraft } from "../types/api";
import type { ConversationRound } from "../lib/groupRounds";
import { messageDedupeKey, messageStableKey, roundStableKey } from "../lib/groupRounds";
import { modelLabel } from "../lib/modelLabel";
import { stripUserMessageWrapper } from "../lib/stripWrapper";
import { usePinScrollBottom } from "../hooks/usePinScrollBottom";
import { StreamingTypewriterText } from "./StreamingTypewriterText";
import { TypewriterText } from "./TypewriterText";

const ACTIVITY_MAX_H = "max-h-48";
const AGENT_CONTENT_MAX_W = "min-w-0 w-full max-w-[90%]";

function ModelBadge({ model }: { model: string }) {
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 font-mono text-[11px] font-medium text-indigo-700"
      title={model}
    >
      {modelLabel(model)}
    </span>
  );
}

function ThoughtBlock({
  text,
  children,
  className = "mb-3",
}: {
  text?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`min-w-0 max-w-full rounded-lg border border-violet-200 bg-violet-50/80 px-3 py-2 text-sm text-slate-700 whitespace-pre-wrap break-words [overflow-wrap:anywhere] ${className}`}
    >
      <span className="text-xs font-medium uppercase tracking-wide text-violet-600">Thinking</span>
      <div className="mt-1">{children ?? text}</div>
    </div>
  );
}

function ToolBlock({
  kind,
  name,
  preview,
  detail,
}: {
  kind: "call" | "result";
  name?: string;
  preview: string;
  detail: string;
}) {
  const [open, setOpen] = useState(false);
  const label = kind === "call" ? "call" : "result";
  const title = name ? `${name}` : "";

  return (
    <div className="min-w-0 max-w-full text-sm border-l-2 border-slate-300 pl-3 py-0.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full min-w-0 text-left text-slate-600 hover:text-slate-900"
      >
        <div className="min-w-0 break-words [overflow-wrap:anywhere]">
          <span className="font-mono text-xs uppercase tracking-wide text-slate-500">{label}</span>
          {title && <span className="font-mono text-slate-700 break-all"> {title}</span>}
          <span className="text-slate-500"> — </span>
          <span className="text-slate-600">{preview}{detail.length > preview.length ? "…" : ""}</span>
        </div>
      </button>
      {open && (
        <pre className="mt-1.5 max-h-64 max-w-full overflow-x-auto overflow-y-auto rounded-md bg-slate-50 p-2 text-xs whitespace-pre-wrap break-all border border-slate-200 text-slate-700">
          {detail}
        </pre>
      )}
    </div>
  );
}

function ToolCallBlock({ name, args }: { name: string; args: Record<string, unknown> }) {
  const detail = JSON.stringify(args, null, 2);
  const preview = JSON.stringify(args).slice(0, 120);
  return <ToolBlock kind="call" name={name} preview={preview} detail={detail} />;
}

function ToolResultBlock({ name, content }: { name?: string; content: string }) {
  const preview = content.slice(0, 120);
  return <ToolBlock kind="result" name={name} preview={preview} detail={content} />;
}

function ActivityMessage({ msg }: { msg: Message }) {
  if (msg.type === "tool") {
    const text = typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content);
    return <ToolResultBlock name={msg.name} content={text} />;
  }
  if (msg.type === "ai") {
    const hasTools = msg.tool_calls && msg.tool_calls.length > 0;
    const text = typeof msg.content === "string" ? msg.content : "";
    return (
      <div className="space-y-2">
        {msg.reasoning && <ThoughtBlock text={msg.reasoning} className="mb-2" />}
        {hasTools &&
          msg.tool_calls!.map((tc, i) => (
            <ToolCallBlock key={i} name={tc.name} args={tc.args} />
          ))}
        {text.trim() && (
          <div className="min-w-0 max-w-full text-xs text-slate-500 italic whitespace-pre-wrap break-words [overflow-wrap:anywhere] border-l-2 border-slate-200 pl-3 py-0.5">
            {text}
          </div>
        )}
      </div>
    );
  }
  return null;
}

function StreamPreviewBlock({
  draft,
  live,
  model,
  onReveal,
}: {
  draft: StreamDraft;
  live: boolean;
  model?: string | null;
  onReveal?: () => void;
}) {
  const streamSessionRef = useRef("");
  if (live && !streamSessionRef.current) {
    streamSessionRef.current = draft.updated_at ?? `stream-${Date.now()}`;
  }
  if (!live) {
    streamSessionRef.current = "";
  }
  const streamSession = streamSessionRef.current;

  const hasReasoning = Boolean(draft.reasoning?.trim());
  const hasContent = Boolean(draft.content?.trim());

  if (!hasReasoning && !hasContent) {
    return (
      <div className="min-w-0 max-w-full text-xs text-slate-500 italic border-l-2 border-amber-300 pl-3 py-0.5">
        Generating
        <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-amber-500 align-middle" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {hasReasoning && (
        <ThoughtBlock className="mb-2">
          <StreamingTypewriterText
            text={draft.reasoning}
            live={live}
            sessionKey={`${streamSession}:reasoning`}
            cursorClassName="bg-violet-400"
            onReveal={onReveal}
          />
        </ThoughtBlock>
      )}
      {hasContent && (
        <div className="min-w-0 max-w-full overflow-hidden rounded-2xl rounded-bl-md border border-amber-200 bg-amber-50/60 px-3.5 py-2 text-sm text-slate-700 shadow-sm">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-[10px] font-medium uppercase tracking-wide text-amber-700">
              Drafting
            </span>
            {model && <ModelBadge model={model} />}
          </div>
          <StreamingTypewriterText
            text={draft.content}
            live={live}
            sessionKey={`${streamSession}:content`}
            cursorClassName="bg-amber-500"
            onReveal={onReveal}
          />
        </div>
      )}
    </div>
  );
}

function AgentActivityBlock({
  activity,
  live = false,
  streamDraft = null,
  model = null,
  followResetKey = 0,
  onStreamGrowth,
}: {
  activity: Message[];
  live?: boolean;
  streamDraft?: StreamDraft | null;
  model?: string | null;
  followResetKey?: number;
  onStreamGrowth?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const tailKey =
    activity.length > 0 ? messageDedupeKey(activity[activity.length - 1], activity.length - 1) : "";

  const followLive = live || Boolean(streamDraft);

  // Inner activity panel scroll — separate auto-follow; shares followResetKey with outer on send.
  const { scrollRef, endRef, onScroll, jumpToBottom, isAtBottom, isAutoFollow, notifyContentGrowth } =
    usePinScrollBottom(
      followLive,
      [
        activity.length,
        tailKey,
        streamDraft?.content?.length ?? 0,
        streamDraft?.reasoning?.length ?? 0,
      ],
      followResetKey,
    );

  const onDraftReveal = () => {
    notifyContentGrowth();
    if (live && isAutoFollow) onStreamGrowth?.();
  };

  if (!activity.length && !streamDraft) return null;

  return (
    <div className={`my-2 ${AGENT_CONTENT_MAX_W}`}>
      <div className="min-w-0 max-w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50/90">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex w-full min-w-0 items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:bg-slate-100/80 rounded-lg"
        >
          <span className="min-w-0 truncate">
            Agent activity ({activity.length} step{activity.length === 1 ? "" : "s"})
            {live && <span className="ml-2 text-amber-600">live</span>}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            {model && <ModelBadge model={model} />}
            <span>{expanded ? "Collapse ▾" : "Expand ▸"}</span>
          </span>
        </button>
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className={`relative overflow-x-hidden overflow-y-auto px-3 pb-3 pt-2 space-y-2 border-t border-slate-200/80 ${
            expanded ? "max-h-[70vh]" : ACTIVITY_MAX_H
          }`}
        >
          {activity.map((msg, i) => (
            <ActivityMessage key={messageStableKey(msg, i)} msg={msg} />
          ))}
          {live && streamDraft && (
            <StreamPreviewBlock draft={streamDraft} live={live} model={model} onReveal={onDraftReveal} />
          )}
          <div ref={endRef} />
          {!isAutoFollow || !isAtBottom ? (
            <button
              type="button"
              onClick={jumpToBottom}
              className="sticky bottom-1 left-1/2 z-10 -translate-x-1/2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow hover:bg-slate-50"
            >
              Latest
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function FinalReply({
  msg,
  animate,
  model,
}: {
  msg: Message;
  animate: boolean;
  model?: string | null;
}) {
  const text = typeof msg.content === "string" ? msg.content : "";
  if (!text.trim() && !msg.reasoning) return null;

  return (
    <div className={`my-3 ${AGENT_CONTENT_MAX_W}`}>
      {model && (
        <div className="mb-1 flex justify-end">
          <ModelBadge model={model} />
        </div>
      )}
      {msg.reasoning && <ThoughtBlock text={msg.reasoning} />}
      {text.trim() && (
        <div className="min-w-0 max-w-full overflow-hidden rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2 text-sm shadow-sm">
          <TypewriterText
            text={text}
            animate={animate}
            messageId={msg.id}
            markdown
          />
        </div>
      )}
    </div>
  );
}

export const ConversationRoundView = memo(function ConversationRoundView({
  round,
  roundIndex,
  animateFinalKey,
  isLastRound,
  threadActive,
  streamDraft = null,
  followResetKey = 0,
  activeTurnModel = null,
  onStreamGrowth,
}: {
  round: ConversationRound;
  roundIndex: number;
  animateFinalKey: string | null;
  isLastRound: boolean;
  threadActive: boolean;
  streamDraft?: StreamDraft | null;
  followResetKey?: number;
  activeTurnModel?: string | null;
  onStreamGrowth?: () => void;
}) {
  const finalKey =
    round.final != null ? messageStableKey(round.final, roundIndex * 1000 + 999) : null;
  const shouldAnimate = Boolean(finalKey && animateFinalKey === finalKey);
  const activityLive = threadActive && isLastRound;

  return (
    <section className="mb-6 min-w-0">
      {round.continuedFromCompaction && (
        <p className={`my-2 text-xs italic text-slate-500 ${AGENT_CONTENT_MAX_W}`}>
          Continued from compacted history (earlier messages were summarized)
        </p>
      )}
      {round.human && (
        <div className="flex justify-end my-3">
          <div className="max-w-[80%] rounded-2xl rounded-br-md bg-indigo-600 px-3.5 py-2 text-sm text-white whitespace-pre-wrap">
            {typeof round.human.content === "string"
              ? stripUserMessageWrapper(round.human.content)
              : JSON.stringify(round.human.content)}
          </div>
        </div>
      )}
      <AgentActivityBlock
        activity={round.activity}
        live={activityLive}
        streamDraft={activityLive ? streamDraft : null}
        model={round.model ?? (activityLive ? activeTurnModel : null)}
        followResetKey={isLastRound ? followResetKey : 0}
        onStreamGrowth={activityLive ? onStreamGrowth : undefined}
      />
      {round.final && (
        <FinalReply msg={round.final} animate={shouldAnimate} model={round.model} />
      )}
    </section>
  );
});

export function SummaryBanner({ summary }: { summary: string }) {
  const [open, setOpen] = useState(false);
  if (!summary.trim()) return null;
  return (
    <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs">
      <button type="button" onClick={() => setOpen(!open)} className="font-medium text-amber-800">
        {open ? "Hide" : "Show"} compaction summary
      </button>
      {open && <div className="mt-2 whitespace-pre-wrap text-slate-700">{summary}</div>}
    </div>
  );
};

export const LogEntry = memo(function LogEntry({ msg }: { msg: Message }) {
  if (msg.type === "human") {
    const text = typeof msg.content === "string"
      ? stripUserMessageWrapper(msg.content)
      : JSON.stringify(msg.content);
    return (
      <div className="flex justify-end my-3">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-indigo-600 px-3.5 py-2 text-sm text-white whitespace-pre-wrap">
          {text}
        </div>
      </div>
    );
  }
  return <ActivityMessage msg={msg} />;
});

export function ConversationLog({
  rounds,
  animateFinalKey,
  threadActive,
  streamDraft = null,
  followResetKey = 0,
  activeTurnModel = null,
  onStreamGrowth,
}: {
  rounds: ConversationRound[];
  animateFinalKey: string | null;
  threadActive: boolean;
  streamDraft?: StreamDraft | null;
  followResetKey?: number;
  activeTurnModel?: string | null;
  onStreamGrowth?: () => void;
}) {
  const lastIndex = rounds.length - 1;
  if (!rounds.length && threadActive && streamDraft) {
    return (
      <section className="mb-6 min-w-0">
        <AgentActivityBlock
          activity={[]}
          live
          streamDraft={streamDraft}
          model={activeTurnModel}
          followResetKey={followResetKey}
          onStreamGrowth={onStreamGrowth}
        />
      </section>
    );
  }
  return (
    <>
      {rounds.map((round, i) => (
        <ConversationRoundView
          key={roundStableKey(round, i)}
          round={round}
          roundIndex={i}
          animateFinalKey={animateFinalKey}
          isLastRound={i === lastIndex}
          threadActive={threadActive}
          streamDraft={i === lastIndex ? streamDraft : null}
          followResetKey={followResetKey}
          activeTurnModel={activeTurnModel}
          onStreamGrowth={onStreamGrowth}
        />
      ))}
    </>
  );
}
