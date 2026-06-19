import { useCallback, useEffect, useRef, useState } from "react";

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
 * Auto-follow is pure state — only attachAutoFollow / disableAutoFollow change it.
 *
 * Enable: jumpToBottom (scroll + attach), followLive rising edge, followResetKey,
 *   or user manually scrolls to strict bottom while detached (attach only, no jump).
 * Disable: explicit user scroll-up input (wheel/key/scrollbar/drag), not layout reflow.
 * While attached, content growth uses a single instant scroll-to-bottom path.
 */
export function usePinScrollBottom(
  followLive: boolean,
  structuralDeps: unknown[] = [],
  followResetKey: number = 0,
) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const userScrollActiveRef = useRef(false);
  const pinningRef = useRef(false);
  const prevFollowLiveRef = useRef(followLive);
  const prevResetKeyRef = useRef<number | null>(null);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

  const syncScrollTopRef = useCallback((el: HTMLElement) => {
    lastScrollTopRef.current = el.scrollTop;
  }, []);

  const scrollToBottomInstant = useCallback(
    (el: HTMLElement) => {
      if (!autoFollowRef.current) return;
      pinningRef.current = true;
      el.scrollTop = el.scrollHeight;
      syncScrollTopRef(el);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          pinningRef.current = false;
        });
      });
    },
    [syncScrollTopRef],
  );

  const disableAutoFollow = useCallback(() => {
    if (!autoFollowRef.current) return;
    autoFollowRef.current = false;
    setIsAutoFollow(false);
  }, []);

  const attachAutoFollow = useCallback(() => {
    if (autoFollowRef.current) return;
    autoFollowRef.current = true;
    setIsAutoFollow(true);
  }, []);

  const enableAutoFollow = useCallback(() => {
    attachAutoFollow();
    const el = scrollRef.current;
    if (el) scrollToBottomInstant(el);
  }, [attachAutoFollow, scrollToBottomInstant]);

  const jumpToBottom = useCallback(() => {
    enableAutoFollow();
  }, [enableAutoFollow]);

  const followIfAuto = useCallback(() => {
    if (!autoFollowRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    scrollToBottomInstant(el);
  }, [scrollToBottomInstant]);

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
    const prevTop = lastScrollTopRef.current;
    const currentTop = el.scrollTop;

    if (pinningRef.current) {
      lastScrollTopRef.current = currentTop;
      return;
    }

    if (userScrollActiveRef.current && currentTop < prevTop - SCROLL_UP_EPSILON) {
      disableAutoFollow();
      userScrollActiveRef.current = false;
    } else if (!autoFollowRef.current && dist <= SCROLL_SNAP_PX) {
      attachAutoFollow();
      scrollToBottomInstant(el);
    }

    lastScrollTopRef.current = currentTop;
  }, [attachAutoFollow, disableAutoFollow, scrollToBottomInstant]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    syncScrollTopRef(el);

    const clearUserScroll = () => {
      userScrollActiveRef.current = false;
    };

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY >= 0) return;
      stopFromUserScrollUp(el, e.target);
    };
    const onPointerDown = (e: PointerEvent) => {
      if (isScrollbarPointer(el, e)) {
        disableAutoFollow();
        return;
      }
      userScrollActiveRef.current = true;
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const scrollUpKeys = ["ArrowUp", "PageUp", "Home"];
      if (scrollUpKeys.includes(e.key)) stopFromUserScrollUp(el, e.target);
    };
    const onTouchStart = () => {
      userScrollActiveRef.current = true;
    };

    const opts: AddEventListenerOptions = { passive: true, capture: true };
    el.addEventListener("wheel", onWheel, opts);
    el.addEventListener("pointerdown", onPointerDown, opts);
    el.addEventListener("keydown", onKeyDown, { capture: true });
    el.addEventListener("touchstart", onTouchStart, opts);
    window.addEventListener("pointerup", clearUserScroll);
    window.addEventListener("pointercancel", clearUserScroll);
    window.addEventListener("touchend", clearUserScroll);
    window.addEventListener("touchcancel", clearUserScroll);
    return () => {
      el.removeEventListener("wheel", onWheel, opts);
      el.removeEventListener("pointerdown", onPointerDown, opts);
      el.removeEventListener("keydown", onKeyDown, { capture: true });
      el.removeEventListener("touchstart", onTouchStart, opts);
      window.removeEventListener("pointerup", clearUserScroll);
      window.removeEventListener("pointercancel", clearUserScroll);
      window.removeEventListener("touchend", clearUserScroll);
      window.removeEventListener("touchcancel", clearUserScroll);
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

  return {
    scrollRef,
    endRef,
    onScroll,
    jumpToBottom,
    isAutoFollow,
    notifyContentGrowth: followIfAuto,
    pinnedRef: autoFollowRef,
  };
}
