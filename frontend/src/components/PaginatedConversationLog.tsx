import { useRef } from "react";
import type { ConversationRound } from "../lib/groupRounds";
import { ConversationLog } from "./LogViewer";
import type { StreamDraft } from "../types/api";
import ScrollToBottom, { useObserveScrollPosition } from "react-scroll-to-bottom";

const LOAD_OLDER_THRESHOLD = 120;
const SCROLL_PANEL_CLASS = "scroll-panel";

function ScrollPositionObserver({
  hasOlder,
  loadingOlder,
  onLoadOlder,
}: {
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => Promise<void>;
}) {
  const loadingRef = useRef(false);
  const prevScrollHeightRef = useRef(0);

  useObserveScrollPosition(
    ({ scrollTop, scrollHeight }) => {
      if (
        scrollTop < LOAD_OLDER_THRESHOLD &&
        hasOlder &&
        !loadingOlder &&
        !loadingRef.current
      ) {
        loadingRef.current = true;
        prevScrollHeightRef.current = scrollHeight;
        void onLoadOlder().finally(() => {
          // Preserve visual scroll position after prepending older messages
          requestAnimationFrame(() => {
            const panel = document.querySelector<HTMLElement>(`.${SCROLL_PANEL_CLASS}`);
            if (panel) {
              panel.scrollTop = panel.scrollHeight - prevScrollHeightRef.current;
            }
          });
          loadingRef.current = false;
        });
      }
    },
    [hasOlder, loadingOlder, onLoadOlder],
  );

  return null;
}

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
}) {
  const hiddenCount = Math.max(0, total - loadedCount);

  return (
    <ScrollToBottom
      mode="bottom"
      className="relative flex min-h-0 min-w-0 flex-1 flex-col"
      scrollViewClassName={`${SCROLL_PANEL_CLASS} px-4 py-3`}
      followButtonClassName="!absolute !bottom-4 !left-1/2 !z-10 !-translate-x-1/2 !rounded-full !border !border-slate-200 !bg-white !px-4 !py-1.5 !text-sm !text-slate-700 !shadow-md hover:!bg-slate-50 !w-auto !h-auto"
    >
      <div className="mx-auto w-full min-w-0 max-w-3xl">
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
        />
      </div>
      <ScrollPositionObserver hasOlder={hasOlder} loadingOlder={loadingOlder} onLoadOlder={onLoadOlder} />
    </ScrollToBottom>
  );
}
