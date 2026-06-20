import { useCallback, useEffect, useRef, useState } from "react";

/** Snap when within this many px of target; also used to re-attach auto-follow at strict bottom. */
const SCROLL_SNAP_PX = 1.5;
/** Animation should feel smooth without delaying detach/attach feedback. */
const SCROLL_EASE = 0.28;
const MAX_SCROLL_STEP_PX = 180;
/** When further than this from the bottom, jump instantly instead of animating — prevents slow
 *  scroll animations on initial load with long history or after loading older messages. */
const LARGE_DISTANCE_PX = 2500;

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

/**
 * Auto-follow is pure state — only attachAutoFollow / disableAutoFollow change it.
 *
 * Enable: jumpToBottom (scroll + attach), followLive rising edge, followResetKey,
 *   or user scrolls to strict bottom while detached.
 * Disable: wheel-up, touch-pan, or scrollbar drag (detected via pointerdown on
 *   the container element itself, not on a child). Keyboard-initiated scrolls
 *   that reach the bottom will re-attach.
 * The animation layer never changes attached state and is cancelled by detach.
 */
export function usePinScrollBottom(
  followLive: boolean,
  structuralDeps: unknown[] = [],
  followResetKey: number = 0,
) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const autoFollowRef = useRef(true);
  const animationRef = useRef(0);
  const prevFollowLiveRef = useRef(followLive);
  const prevResetKeyRef = useRef<number | null>(null);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

  const stopAnimation = useCallback(() => {
    if (!animationRef.current) return;
    cancelAnimationFrame(animationRef.current);
    animationRef.current = 0;
  }, []);

  /** Timestamp of last user-initiated scroll (wheel, touch, scrollbar, keyboard, etc.).
   *  Used to prevent instant jumps that would fight recent user interaction. */
  const lastUserScrollRef = useRef(0);

  /** Set when pointerdown fires directly on the scroll container (not a child).
   *  Cleared by the next onScroll that uses it. This detects scrollbar drag uniquely:
   *  only scrollbar clicks land on the container itself, not on content children. */
  const pointerDownOnContainerRef = useRef(false);

  const animateToBottom = useCallback(
    (el: HTMLElement) => {
      if (!autoFollowRef.current) return;
      if (animationRef.current) return;

      const tick = () => {
        if (!autoFollowRef.current) {
          animationRef.current = 0;
          return;
        }

        const target = Math.max(0, el.scrollHeight - el.clientHeight);
        const dist = target - el.scrollTop;

        if (dist <= SCROLL_SNAP_PX) {
          el.scrollTop = target;
          animationRef.current = 0;
          return;
        }

        // Large distance → jump instantly so the user isn't waiting for animation.
        // Skip the instant jump if the user interacted recently (gives them a chance
        // to cancel via wheel/touch before being yanked back).
        if (dist > LARGE_DISTANCE_PX && Date.now() - lastUserScrollRef.current > 500) {
          el.scrollTop = target;
          animationRef.current = 0;
          return;
        }

        const step = Math.min(Math.max(dist * SCROLL_EASE, 1), MAX_SCROLL_STEP_PX);
        el.scrollTop += step;
        animationRef.current = requestAnimationFrame(tick);
      };

      animationRef.current = requestAnimationFrame(tick);
    },
    [],
  );

  const disableAutoFollow = useCallback(() => {
    if (!autoFollowRef.current) return;
    stopAnimation();
    autoFollowRef.current = false;
    setIsAutoFollow(false);
  }, [stopAnimation]);

  const attachAutoFollow = useCallback(() => {
    if (autoFollowRef.current) return;
    autoFollowRef.current = true;
    setIsAutoFollow(true);
  }, []);

  const enableAutoFollow = useCallback(() => {
    attachAutoFollow();
    const el = scrollRef.current;
    if (el) animateToBottom(el);
  }, [animateToBottom, attachAutoFollow]);

  const jumpToBottom = useCallback(() => {
    enableAutoFollow();
  }, [enableAutoFollow]);

  const followIfAuto = useCallback(() => {
    if (!autoFollowRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    animateToBottom(el);
  }, [animateToBottom]);

  const stopFromUserScrollUp = useCallback(
    () => {
      // Intentionally NOT checking nestedScrollableBetween — user control must
      // always win. Any upward wheel / touch move immediately disables auto-follow
      // and cancels the animation, even if the event target is inside a nested
      // scrollable like a code block.
      disableAutoFollow();
    },
    [disableAutoFollow],
  );

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    const dfb = distanceFromBottom(el);

    // Scrollbar drag: a pointerdown directly on the container (not on a child)
    // means the user interacted with the scrollbar. The scroll that follows is
    // user-initiated → detach. Animation never sets pointerDownOnContainerRef.
    if (autoFollowRef.current && dfb > SCROLL_SNAP_PX && pointerDownOnContainerRef.current) {
      pointerDownOnContainerRef.current = false;
      lastUserScrollRef.current = Date.now();
      disableAutoFollow();
      return;
    }

    // User scrolled to strict bottom while detached → re-attach.
    if (!autoFollowRef.current && dfb <= SCROLL_SNAP_PX) {
      attachAutoFollow();
      stopAnimation();
    }
  }, [attachAutoFollow, disableAutoFollow, stopAnimation]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY >= 0) return;
      lastUserScrollRef.current = Date.now();
      stopFromUserScrollUp();
    };
    const onTouchMove = () => {
      lastUserScrollRef.current = Date.now();
      stopFromUserScrollUp();
    };

    const opts: AddEventListenerOptions = { passive: true, capture: true };
    el.addEventListener("wheel", onWheel, opts);
    el.addEventListener("touchmove", onTouchMove, opts);
    return () => {
      el.removeEventListener("wheel", onWheel, opts);
      el.removeEventListener("touchmove", onTouchMove, opts);
      stopAnimation();
    };
  }, [disableAutoFollow, stopAnimation, stopFromUserScrollUp]);

  /** Detect scrollbar drag: pointerdown directly on the container (not a child element)
   *  means the user clicked the scrollbar track or thumb. The flag is consumed by onScroll
   *  on the next scroll event, which detaches auto-follow. */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onPointerDown = (e: PointerEvent) => {
      if (e.target === el) {
        pointerDownOnContainerRef.current = true;
      }
    };
    el.addEventListener("pointerdown", onPointerDown, true);
    return () => el.removeEventListener("pointerdown", onPointerDown, true);
  }, []);

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
