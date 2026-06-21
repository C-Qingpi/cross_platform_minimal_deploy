import { useCallback, useRef } from "react";
import type { ConversationRound } from "../lib/groupRounds";
import { ConversationLog, SummaryBanner } from "./LogViewer";
import type { StreamDraft } from "../types/api";
import { usePinScrollBottom } from "../hooks/usePinScrollBottom";

const LOAD_OLDER_THRESHOLD = 120;

export function PaginatedConversationLog({
  rounds,
  summary,
  animateFinalKey,
  hasOlder,
  loadingOlder,
  total,
  loadedCount,
  threadActive,
  streamDraft = null,
  activeTurnModel = null,
  followResetKey = 0,
  onLoadOlder,
}: {
  rounds: ConversationRound[];
  summary: string;
  animateFinalKey: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  total: number;
  loadedCount: number;
  threadActive: boolean;
  streamDraft?: StreamDraft | null;
  activeTurnModel?: string | null;
  followResetKey?: number;
  onLoadOlder: () => Promise<void>;
}) {
  const loadingOlderRef = useRef(false);

  // Outer message log scroll — independent auto-follow from inner activity panel.
  const { scrollRef, endRef, onScroll: onPinScroll, jumpToBottom, isAutoFollow, notifyContentGrowth } =
    usePinScrollBottom(
      [
        rounds.length,
        total,
        animateFinalKey,
        streamDraft?.content?.length ?? 0,
        streamDraft?.reasoning?.length ?? 0,
      ],
      followResetKey,
      "outer",
    );

  const onScroll = useCallback(() => {
    onPinScroll();
    const el = scrollRef.current;
    if (!el) return;

    if (el.scrollTop < LOAD_OLDER_THRESHOLD && hasOlder && !loadingOlderRef.current) {
      loadingOlderRef.current = true;
      const prevHeight = el.scrollHeight;
      const prevTop = el.scrollTop;
      void onLoadOlder().finally(() => {
        loadingOlderRef.current = false;
        requestAnimationFrame(() => {
          const node = scrollRef.current;
          if (!node) return;
          node.scrollTop = node.scrollHeight - prevHeight + prevTop;
        });
      });
    }
  }, [hasOlder, onLoadOlder, onPinScroll, scrollRef]);

  const hiddenCount = Math.max(0, total - loadedCount);

  return (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      <main
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-3 min-h-0"
      >
        <div className="mx-auto w-full min-w-0 max-w-3xl">
          <SummaryBanner summary={summary} />

          {(hasOlder || loadingOlder) && (
            <div className="mb-3 text-center text-xs text-slate-500">
              {loadingOlder
                ? "Loading older messages…"
                : hiddenCount > 0
                  ? `${hiddenCount.toLocaleString()} older message${hiddenCount === 1 ? "" : "s"} — scroll up`
                  : "Scroll up for older messages"}
            </div>
          )}

          <ConversationLog
            rounds={rounds}
            animateFinalKey={animateFinalKey}
            threadActive={threadActive}
            streamDraft={streamDraft}
            activeTurnModel={activeTurnModel}
            followResetKey={followResetKey}
            onStreamGrowth={notifyContentGrowth}
          />
          <div ref={endRef} />
        </div>
      </main>

      {!isAutoFollow ? (
        <button
          type="button"
          onClick={jumpToBottom}
          className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-sm text-slate-700 shadow-md hover:bg-slate-50"
        >
          Jump to latest
        </button>
      ) : null}
    </div>
  );
}
