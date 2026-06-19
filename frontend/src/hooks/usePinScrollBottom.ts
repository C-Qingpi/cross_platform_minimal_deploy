import { useCallback, useEffect, useRef, useState } from "react";

/** Show jump/latest button when roughly near bottom. */
const BOTTOM_THRESHOLD = 48;
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
 * Disable: any user scroll-up on THIS container (even 1px).
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
  const prevFollowLiveRef = useRef(followLive);
  const prevResetKeyRef = useRef<number | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

  const syncScrollTopRef = useCallback((el: HTMLElement) => {
    lastScrollTopRef.current = el.scrollTop;
  }, []);

  const scrollToBottomInstant = useCallback(
    (el: HTMLElement) => {
      if (!autoFollowRef.current) return;
      el.scrollTop = el.scrollHeight;
      syncScrollTopRef(el);
    },
    [syncScrollTopRef],
  );

  const disableAutoFollow = useCallback(() => {
    autoFollowRef.current = false;
    setIsAutoFollow(false);
  }, []);

  const attachAutoFollow = useCallback(() => {
    autoFollowRef.current = true;
    setIsAutoFollow(true);
  }, []);

  const enableAutoFollow = useCallback(() => {
    attachAutoFollow();
    const el = scrollRef.current;
    if (el) {
      scrollToBottomInstant(el);
      setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
    } else {
      setIsAtBottom(true);
    }
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
    setIsAtBottom(dist <= BOTTOM_THRESHOLD);

    const prevTop = lastScrollTopRef.current;
    const currentTop = el.scrollTop;

    if (currentTop < prevTop - SCROLL_UP_EPSILON) {
      disableAutoFollow();
    } else if (!autoFollowRef.current && dist <= SCROLL_SNAP_PX) {
      attachAutoFollow();
      setIsAtBottom(true);
    }

    lastScrollTopRef.current = currentTop;
  }, [attachAutoFollow, disableAutoFollow]);

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
