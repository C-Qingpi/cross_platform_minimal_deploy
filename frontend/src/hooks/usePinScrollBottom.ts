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

  /** True only during the synchronous execution of the animation tick function — specifically
   *  during `el.scrollTop` assignments. Used by onScroll to distinguish animation-propagated
   *  scroll events from real user-initiated ones (keyboard, middle-click, scrollbar arrows, etc.).
   *  This is a synchronous flag, not async, so there is no race: the scroll event from
   *  `el.scrollTop += step` fires synchronously while this is true. */
  const isAnimationTickRef = useRef(false);

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
          isAnimationTickRef.current = true;
          el.scrollTop = target;
          isAnimationTickRef.current = false;
          animationRef.current = 0;
          return;
        }

        // Large distance → jump instantly so the user isn't waiting for animation.
        // Skip the instant jump if the user interacted recently (gives them a chance
        // to cancel via wheel/touch before being yanked back).
        if (dist > LARGE_DISTANCE_PX && Date.now() - lastUserScrollRef.current > 500) {
          isAnimationTickRef.current = true;
          el.scrollTop = target;
          isAnimationTickRef.current = false;
          animationRef.current = 0;
          return;
        }

        const step = Math.min(Math.max(dist * SCROLL_EASE, 1), MAX_SCROLL_STEP_PX);
        isAnimationTickRef.current = true;
        el.scrollTop += step;
        isAnimationTickRef.current = false;
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

    // Any non-animation scroll that moves away from bottom = user interaction → detach.
    // Covers: wheel, touch, scrollbar drag, keyboard (Page Up/Down, arrows, Home/End),
    // middle-click drag, scrollbar arrows, auto-scroll extensions — everything.
    // The isAnimationTickRef flag is set synchronously around el.scrollTop assignments
    // inside the animation tick, so animation-propagated scroll events never reach here.
    if (autoFollowRef.current && dfb > SCROLL_SNAP_PX && !isAnimationTickRef.current) {
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

  /** Scrollbar click: pointerdown directly on the container (not a child element)
   *  means the user clicked the scrollbar track or thumb. Detach immediately. */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onPointerDown = (e: PointerEvent) => {
      if (e.target === el) {
        lastUserScrollRef.current = Date.now();
        disableAutoFollow();
      }
    };
    el.addEventListener("pointerdown", onPointerDown, true);
    return () => el.removeEventListener("pointerdown", onPointerDown, true);
  }, [disableAutoFollow]);

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
