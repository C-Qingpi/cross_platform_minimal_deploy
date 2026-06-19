import { useCallback, useEffect, useRef, useState } from "react";

/** Show jump/latest button when roughly near bottom. */
const BOTTOM_THRESHOLD = 48;
/** Ease toward bottom each frame during live follow (higher = snappier). */
const SCROLL_EASE = 0.22;
/** Snap when within this many px of target. */
const SCROLL_SNAP_PX = 1.5;

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
 * Enable: jumpToBottom, followLive rising edge, followResetKey (send message).
 * Disable: user scroll input on THIS container, or user manually hits strict bottom.
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
  const userScrollRef = useRef(false);
  const prevFollowLiveRef = useRef(followLive);
  const prevResetKeyRef = useRef<number | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

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
    programmaticRafRef.current = requestAnimationFrame(() => {
      programmaticRafRef.current = requestAnimationFrame(() => {
        programmaticRafRef.current = 0;
        programmaticRef.current = false;
      });
    });
  }, [clearProgrammatic, stopSmoothScroll]);

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
        programmaticRef.current = false;
        smoothScrollRafRef.current = 0;
        setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
        return;
      }

      el.scrollTop = current + dist * SCROLL_EASE;
      setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
      smoothScrollRafRef.current = requestAnimationFrame(tick);
    };

    smoothScrollRafRef.current = requestAnimationFrame(tick);
  }, []);

  const disableAutoFollow = useCallback(() => {
    autoFollowRef.current = false;
    setIsAutoFollow(false);
    userScrollRef.current = false;
    stopSmoothScroll();
    clearProgrammatic();
  }, [clearProgrammatic, stopSmoothScroll]);

  const enableAutoFollow = useCallback(() => {
    autoFollowRef.current = true;
    setIsAutoFollow(true);
    userScrollRef.current = false;
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

  const markUserScroll = useCallback(() => {
    userScrollRef.current = true;
  }, []);

  const stopFromUserInput = useCallback(
    (el: HTMLElement, target: EventTarget | null) => {
      if (nestedScrollableBetween(el, target)) return;
      markUserScroll();
      disableAutoFollow();
    },
    [disableAutoFollow, markUserScroll],
  );

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    const dist = distanceFromBottom(el);
    setIsAtBottom(dist <= BOTTOM_THRESHOLD);

    if (programmaticRef.current) return;

    if (userScrollRef.current) {
      disableAutoFollow();
    }
  }, [disableAutoFollow]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => stopFromUserInput(el, e.target);
    const onTouchMove = (e: TouchEvent) => stopFromUserInput(el, e.target);
    const onPointerDown = (e: PointerEvent) => {
      if (isScrollbarPointer(el, e)) {
        markUserScroll();
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const scrollKeys = ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "];
      if (scrollKeys.includes(e.key)) stopFromUserInput(el, e.target);
    };

    const opts: AddEventListenerOptions = { passive: true, capture: true };
    el.addEventListener("wheel", onWheel, opts);
    el.addEventListener("touchmove", onTouchMove, opts);
    el.addEventListener("pointerdown", onPointerDown, opts);
    el.addEventListener("keydown", onKeyDown, { capture: true });
    return () => {
      el.removeEventListener("wheel", onWheel, opts);
      el.removeEventListener("touchmove", onTouchMove, opts);
      el.removeEventListener("pointerdown", onPointerDown, opts);
      el.removeEventListener("keydown", onKeyDown, { capture: true });
    };
  }, [markUserScroll, stopFromUserInput]);

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
