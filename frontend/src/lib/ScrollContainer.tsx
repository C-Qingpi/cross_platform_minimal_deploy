/**
 * Lightweight scroll container with instant-bottom and sticky-follow.
 *
 * Replaces react-scroll-to-bottom which always animates the first scroll via
 * useLayoutEffect-driven SpineTo, regardless of initialScrollBehavior.
 *
 * - First mount: instant scrollTop = scrollHeight (before paint via useLayoutEffect)
 * - Content changes while sticky: instant scrollTop = scrollHeight (MutationObserver)
 * - "Scroll to bottom" button shown when user scrolls away
 * - useObserveScrollPosition() for load-older detection
 */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

// ── Public markers preserved from react-scroll-to-bottom ────────────────
export const SCROLL_PANEL_CLASS = "scroll-panel";

export interface ScrollPosition {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

type ObserverFn = (pos: ScrollPosition) => void;
type UnsubscribeFn = () => void;

// ── Context ─────────────────────────────────────────────────────────────
const ScrollCtx = createContext<{
  observe: (fn: ObserverFn) => UnsubscribeFn;
} | null>(null);

/**
 * Mirrors react-scroll-to-bottom's useObserveScrollPosition(observer, deps).
 * Subscribes when observer is truthy, unsubscribes on cleanup.
 */
export function useObserveScrollPosition(
  observer: ((pos: { scrollTop: number; scrollHeight: number }) => void) | null,
  deps?: unknown[],
): void {
  const ctx = useContext(ScrollCtx);
  const observerRef = useRef(observer);
  observerRef.current = observer;

  useEffect(() => {
    if (!ctx || !observer) return;
    const wrapper = (pos: ScrollPosition) =>
      observerRef.current?.({ scrollTop: pos.scrollTop, scrollHeight: pos.scrollHeight });
    const unsub = ctx.observe(wrapper);
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps ? [ctx, ...deps] : [ctx]);
}

// ── Constants ───────────────────────────────────────────────────────────
const PROXIMITY = 64; // px threshold for "at bottom"

// ── Component ───────────────────────────────────────────────────────────
export interface ScrollContainerProps {
  className?: string;
  scrollViewClassName?: string;
  followButtonClassName?: string;
  children: ReactNode;
}

export function ScrollContainer({
  className = "",
  scrollViewClassName = "",
  followButtonClassName = "",
  children,
}: ScrollContainerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const stickyRef = useRef(true);
  const prevScrollHeightRef = useRef(0);
  const observerSetRef = useRef(new Set<ObserverFn>());
  /** Prevents MutationObserver from reacting to our own instant scroll */
  const programmaticScrollRef = useRef(false);

  // ── observer management ───────────────────────────────────────────
  const observe = useCallback((fn: ObserverFn): UnsubscribeFn => {
    observerSetRef.current.add(fn);
    // Call immediately
    const p = panelRef.current;
    if (p) fn({ scrollTop: p.scrollTop, scrollHeight: p.scrollHeight, clientHeight: p.clientHeight });
    return () => { observerSetRef.current.delete(fn); };
  }, []);

  const notify = useCallback(() => {
    const p = panelRef.current;
    if (!p) return;
    const pos: ScrollPosition = {
      scrollTop: p.scrollTop,
      scrollHeight: p.scrollHeight,
      clientHeight: p.clientHeight,
    };
    observerSetRef.current.forEach((fn) => fn(pos));
  }, []);

  // ── scroll to bottom (teleport) ───────────────────────────────────
  const teleport = useCallback(() => {
    const p = panelRef.current;
    if (!p) return;
    programmaticScrollRef.current = true;
    p.scrollTop = p.scrollHeight;
    // Reset in next frame
    requestAnimationFrame(() => { programmaticScrollRef.current = false; });
    stickyRef.current = true;
    setAtBottom(true);
  }, []);

  // ── is-at-bottom check ────────────────────────────────────────────
  const checkAtBottom = useCallback((p: HTMLElement) => {
    const isAtBottom = p.scrollHeight - p.scrollTop - p.clientHeight < PROXIMITY;
    setAtBottom(isAtBottom);
  }, []);

  // ── initial instant scroll (before paint) ─────────────────────────
  useLayoutEffect(() => {
    teleport();
  }, [teleport]);

  // ── content-change sticky + scroll listener ───────────────────────
  useEffect(() => {
    const p = panelRef.current;
    if (!p) return;

    const onScroll = () => {
      if (programmaticScrollRef.current) return;
      const isAtBottom = p.scrollHeight - p.scrollTop - p.clientHeight < PROXIMITY;
      stickyRef.current = isAtBottom;
      checkAtBottom(p);
      notify();
    };

    const mo = new MutationObserver(() => {
      const newH = p.scrollHeight;
      if (newH !== prevScrollHeightRef.current && stickyRef.current) {
        teleport();
      }
      prevScrollHeightRef.current = newH;
      checkAtBottom(p);
      notify();
    });
    mo.observe(p, { childList: true, subtree: true, characterData: true });

    p.addEventListener("scroll", onScroll, { passive: true });
    checkAtBottom(p);
    notify();

    return () => {
      p.removeEventListener("scroll", onScroll);
      mo.disconnect();
    };
  }, [checkAtBottom, notify, teleport]);

  const ctx = useMemo(() => ({ observe }), [observe]);

  const followBtnDefault =
    "!absolute !bottom-4 !left-1/2 !z-10 !-translate-x-1/2 !rounded-full !border !border-slate-200 !bg-white !px-4 !py-1.5 !text-sm !text-slate-700 !shadow-md hover:!bg-slate-50";
  const followBtn = followButtonClassName || followBtnDefault;

  return (
    <ScrollCtx.Provider value={ctx}>
      <div className={className} style={{ position: "relative" }}>
        <div
          ref={panelRef}
          className={`${SCROLL_PANEL_CLASS} ${scrollViewClassName}`}
          style={{ height: "100%", overflowY: "auto", width: "100%" }}
        >
          {children}
        </div>
        {!atBottom && (
          <button type="button" onClick={teleport} className={followBtn}>
            ↓ Jump to bottom
          </button>
        )}
      </div>
    </ScrollCtx.Provider>
  );
}

export default ScrollContainer;
