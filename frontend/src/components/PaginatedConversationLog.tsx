import { useCallback, useEffect, useRef, useState } from "react";
import type { ConversationRound } from "../lib/groupRounds";
import { ConversationLog } from "./LogViewer";
import type { StreamDraft } from "../types/api";
import {
  ScrollContainer,
  useObserveScrollPosition,
  SCROLL_PANEL_CLASS,
} from "../lib/ScrollContainer";

const LOAD_OLDER_THRESHOLD = 120;
const BOTTOM_THRESHOLD = 64;

/**
 * Paginated conversation log with lazy loading:
 *
 * - Near top + hasOlder → auto-trigger loadOlder.
 *   Visual position is preserved after prepend so the user must
 *   scroll past the newly-loaded content to trigger again.
 *
 * - At bottom + has loaded older pages → auto-discard to keep
 *   the virtual list small.
 */
export function PaginatedConversationLog({
  rounds,
  animateFinalKey,
  hasOlder,
  loadingOlder,
  total,
  loadedCount,
  threadActive,
  streamDraft = null,
  activeTurnModel = null,
  onLoadOlder,
  onDiscardOlder,
}: {
  rounds: ConversationRound[];
  animateFinalKey: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  total: number;
  loadedCount: number;
  threadActive: boolean;
  streamDraft?: StreamDraft | null;
  activeTurnModel?: string | null;
  onLoadOlder: () => Promise<void>;
  onDiscardOlder: () => void;
}) {
  const loadingRef = useRef(false);
  const prevScrollHeightRef = useRef(0);

  const [nearTop, setNearTop] = useState(false);
  const wasAtBottomRef = useRef(false);

  // ── Scroll observer: auto-load near top, auto-discard at bottom
  useObserveScrollPosition(({ scrollTop, scrollHeight, clientHeight }) => {
    setNearTop(scrollTop < LOAD_OLDER_THRESHOLD);

    const atBottom =
      scrollHeight - scrollTop - clientHeight < BOTTOM_THRESHOLD;
    if (atBottom && !wasAtBottomRef.current) {
      onDiscardOlder();
    }
    wasAtBottomRef.current = atBottom;
  });

  // ── Auto-trigger loadOlder when near top ─────────────────────
  const triggerLoad = useCallback(async () => {
    if (loadingRef.current || loadingOlder) return;
    loadingRef.current = true;
    const panel = document.querySelector<HTMLElement>(`.${SCROLL_PANEL_CLASS}`);
    if (panel) prevScrollHeightRef.current = panel.scrollHeight;

    try {
      await onLoadOlder();
    } finally {
      requestAnimationFrame(() => {
        const p = document.querySelector<HTMLElement>(`.${SCROLL_PANEL_CLASS}`);
        if (p) {
          p.scrollTop = p.scrollHeight - prevScrollHeightRef.current;
        }
        loadingRef.current = false;
      });
    }
  }, [loadingOlder, onLoadOlder]);

  useEffect(() => {
    if (nearTop && hasOlder && !loadingOlder && !loadingRef.current) {
      triggerLoad();
    }
  }, [nearTop, hasOlder, loadingOlder, triggerLoad]);

  const hiddenCount = Math.max(0, total - loadedCount);

  return (
    <ScrollContainer
      className="relative flex min-h-0 min-w-0 flex-1 flex-col"
      scrollViewClassName={"px-4 py-3"}
      followButtonClassName="!absolute !bottom-4 !left-1/2 !z-10 !-translate-x-1/2 !rounded-full !border !border-slate-200 !bg-white !px-4 !py-1.5 !text-sm !text-slate-700 !shadow-md hover:!bg-slate-50 !w-auto !h-auto"
    >
      <div className="mx-auto w-full min-w-0 max-w-3xl">
        {/* ── Pagination indicator ──────────────────────────────── */}
        {(hasOlder || loadingOlder) && nearTop && (
          <div className="mb-3 text-center text-xs text-slate-400">
            {loadingOlder ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
                Loading older messages…
              </span>
            ) : hiddenCount > 0 ? (
              <>{hiddenCount.toLocaleString()} older message{hiddenCount === 1 ? "" : "s"} above</>
            ) : (
              "Scroll up for older messages"
            )}
          </div>
        )}

        {!hasOlder && total > 0 && loadedCount > 0 && nearTop && (
          <div className="mb-3 text-center text-xs text-slate-400">
            Beginning of conversation
          </div>
        )}

        <ConversationLog
          rounds={rounds}
          animateFinalKey={animateFinalKey}
          threadActive={threadActive}
          streamDraft={streamDraft}
          activeTurnModel={activeTurnModel}
        />
      </div>
    </ScrollContainer>
  );
}
