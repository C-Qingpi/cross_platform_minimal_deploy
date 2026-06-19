import { useCallback, useEffect, useRef, useState } from "react";

/** Show jump/latest button when roughly near bottom. */
const BOTTOM_THRESHOLD = 48;
/** Ease toward bottom each frame during live follow (higher = snappier). */
const SCROLL_EASE = 0.22;
/** Snap when within this many px of target; also used to re-attach auto-follow at strict bottom. */
const SCROLL_SNAP_PX = 1.5;
/** Treat this many px of upward scrollTop as intentional user scroll-up. */
const SCROLL_UP_EPSILON = 0.5;

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

function isScrollableY(node: HTMLElement): boolean {
  if (node.scrollHeight <= node.clientHeight) return false;
  const oy = getComputedStyle(node).overflowY;
  return oy === "auto" || oy === "scroll" || oy === "overlay";
}

/** Wheel/scroll on a nested overflow panel should not affect this container. */
function nestedScrollableBetween(el: HTMLElement, target: EventTarget | null): HTMLElement | null {
  let node = target instanceof Node ? target : null;
  while (node && node !== el) {
    if (node instanceof HTMLElement && isScrollableY(node)) return node;
    node = node.parentNode;
  }
  return null;
}

function isScrollbarPointer(el: HTMLElement, e: PointerEvent): boolean {
  const barW = el.offsetWidth - el.clientWidth;
  if (barW <= 0) return false;
  const rect = el.getBoundingClientRect();
  return e.clientX >= rect.right - barW;
}

/**
 * Auto-follow is pure state — only enableAutoFollow / disableAutoFollow change it.
 *
 * Enable: jumpToBottom, followLive rising edge, followResetKey (send message),
 *   or user manually scrolls to strict bottom while detached.
 * Disable: any user scroll-up on THIS container (even 1px).
 * Content growth only scrolls while auto-follow is on; never toggles the flag.
 */
export function usePinScrollBottom(
  followLive: boolean,
  structuralDeps: unknown[] = [],
  followResetKey: number = 0,
) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const programmaticRef = useRef(false);
  const programmaticRafRef = useRef(0);
  const smoothScrollRafRef = useRef(0);
  const lastScrollTopRef = useRef(0);
  const prevFollowLiveRef = useRef(followLive);
  const prevResetKeyRef = useRef<number | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

  const syncScrollTopRef = useCallback((el: HTMLElement) => {
    lastScrollTopRef.current = el.scrollTop;
  }, []);

  const clearProgrammatic = useCallback(() => {
    programmaticRef.current = false;
    if (programmaticRafRef.current) {
      cancelAnimationFrame(programmaticRafRef.current);
      programmaticRafRef.current = 0;
    }
  }, []);

  const stopSmoothScroll = useCallback(() => {
    if (smoothScrollRafRef.current) {
      cancelAnimationFrame(smoothScrollRafRef.current);
      smoothScrollRafRef.current = 0;
    }
  }, []);

  const scrollToBottomInstant = useCallback((el: HTMLElement) => {
    if (!autoFollowRef.current) return;
    stopSmoothScroll();
    clearProgrammatic();
    programmaticRef.current = true;
    el.scrollTop = el.scrollHeight;
    syncScrollTopRef(el);
    programmaticRafRef.current = requestAnimationFrame(() => {
      programmaticRafRef.current = requestAnimationFrame(() => {
        programmaticRafRef.current = 0;
        programmaticRef.current = false;
      });
    });
  }, [clearProgrammatic, stopSmoothScroll, syncScrollTopRef]);

  const scrollToBottomSmooth = useCallback((el: HTMLElement) => {
    if (!autoFollowRef.current) return;
    if (smoothScrollRafRef.current) return;

    const tick = () => {
      if (!autoFollowRef.current) {
        smoothScrollRafRef.current = 0;
        programmaticRef.current = false;
        return;
      }

      programmaticRef.current = true;
      const target = Math.max(0, el.scrollHeight - el.clientHeight);
      const current = el.scrollTop;
      const dist = target - current;

      if (dist <= SCROLL_SNAP_PX) {
        el.scrollTop = target;
        syncScrollTopRef(el);
        programmaticRef.current = false;
        smoothScrollRafRef.current = 0;
        setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
        return;
      }

      el.scrollTop = current + dist * SCROLL_EASE;
      syncScrollTopRef(el);
      setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
      smoothScrollRafRef.current = requestAnimationFrame(tick);
    };

    smoothScrollRafRef.current = requestAnimationFrame(tick);
  }, [syncScrollTopRef]);

  const disableAutoFollow = useCallback(() => {
    autoFollowRef.current = false;
    setIsAutoFollow(false);
    stopSmoothScroll();
    clearProgrammatic();
  }, [clearProgrammatic, stopSmoothScroll]);

  const enableAutoFollow = useCallback(() => {
    autoFollowRef.current = true;
    setIsAutoFollow(true);
    const el = scrollRef.current;
    if (el) {
      scrollToBottomInstant(el);
      setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
    } else {
      setIsAtBottom(true);
    }
  }, [scrollToBottomInstant]);

  const jumpToBottom = useCallback(() => {
    enableAutoFollow();
  }, [enableAutoFollow]);

  const followIfAuto = useCallback(() => {
    if (!autoFollowRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    scrollToBottomSmooth(el);
  }, [scrollToBottomSmooth]);

  const stopFromUserScrollUp = useCallback(
    (el: HTMLElement, target: EventTarget | null) => {
      if (nestedScrollableBetween(el, target)) return;
      disableAutoFollow();
    },
    [disableAutoFollow],
  );

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    const dist = distanceFromBottom(el);
    setIsAtBottom(dist <= BOTTOM_THRESHOLD);

    const prevTop = lastScrollTopRef.current;
    const currentTop = el.scrollTop;

    if (currentTop < prevTop - SCROLL_UP_EPSILON) {
      disableAutoFollow();
    } else if (!autoFollowRef.current && dist <= SCROLL_SNAP_PX) {
      enableAutoFollow();
    }

    lastScrollTopRef.current = currentTop;
  }, [disableAutoFollow, enableAutoFollow]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    syncScrollTopRef(el);

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY >= 0) return;
      stopFromUserScrollUp(el, e.target);
    };
    const onPointerDown = (e: PointerEvent) => {
      if (isScrollbarPointer(el, e)) {
        disableAutoFollow();
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const scrollUpKeys = ["ArrowUp", "PageUp", "Home"];
      if (scrollUpKeys.includes(e.key)) stopFromUserScrollUp(el, e.target);
    };

    const opts: AddEventListenerOptions = { passive: true, capture: true };
    el.addEventListener("wheel", onWheel, opts);
    el.addEventListener("pointerdown", onPointerDown, opts);
    el.addEventListener("keydown", onKeyDown, { capture: true });
    return () => {
      el.removeEventListener("wheel", onWheel, opts);
      el.removeEventListener("pointerdown", onPointerDown, opts);
      el.removeEventListener("keydown", onKeyDown, { capture: true });
    };
  }, [disableAutoFollow, stopFromUserScrollUp, syncScrollTopRef]);

  useEffect(() => {
    if (followLive && !prevFollowLiveRef.current) {
      enableAutoFollow();
    }
    prevFollowLiveRef.current = followLive;
  }, [followLive, enableAutoFollow]);

  useEffect(() => {
    if (followResetKey === prevResetKeyRef.current) return;
    prevResetKeyRef.current = followResetKey;
    enableAutoFollow();
  }, [followResetKey, enableAutoFollow]);

  useEffect(() => {
    followIfAuto();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, structuralDeps);

  useEffect(() => {
    if (!followLive) return;

    let ro: ResizeObserver | null = null;

    const observeContent = () => {
      const content = endRef.current?.parentElement;
      if (!content || ro) return;
      ro = new ResizeObserver(() => followIfAuto());
      ro.observe(content);
    };

    observeContent();
    const mo = new MutationObserver(observeContent);
    if (scrollRef.current) {
      mo.observe(scrollRef.current, { childList: true, subtree: true });
    }

    return () => {
      ro?.disconnect();
      mo.disconnect();
      stopSmoothScroll();
    };
  }, [followLive, followIfAuto, stopSmoothScroll]);

  return {
    scrollRef,
    endRef,
    onScroll,
    jumpToBottom,
    isAtBottom,
    isAutoFollow,
    notifyContentGrowth: followIfAuto,
    pinnedRef: autoFollowRef,
  };
}
