import { useCallback, useEffect, useRef, useState } from "react";

/** Show jump/latest button when roughly near bottom. */
const BOTTOM_THRESHOLD = 48;

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

  const disableAutoFollow = useCallback(() => {
    autoFollowRef.current = false;
    setIsAutoFollow(false);
    userScrollRef.current = false;
    clearProgrammatic();
  }, [clearProgrammatic]);

  const scrollToBottom = useCallback((el: HTMLElement) => {
    if (!autoFollowRef.current) return;
    clearProgrammatic();
    programmaticRef.current = true;
    el.scrollTop = el.scrollHeight;
    programmaticRafRef.current = requestAnimationFrame(() => {
      programmaticRafRef.current = requestAnimationFrame(() => {
        programmaticRafRef.current = 0;
        programmaticRef.current = false;
      });
    });
  }, [clearProgrammatic]);

  const enableAutoFollow = useCallback(() => {
    autoFollowRef.current = true;
    setIsAutoFollow(true);
    userScrollRef.current = false;
    const el = scrollRef.current;
    if (el) {
      scrollToBottom(el);
      setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
    } else {
      setIsAtBottom(true);
    }
  }, [scrollToBottom]);

  const jumpToBottom = useCallback(() => {
    enableAutoFollow();
  }, [enableAutoFollow]);

  const followIfAuto = useCallback(() => {
    if (!autoFollowRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    scrollToBottom(el);
    setIsAtBottom(distanceFromBottom(el) <= BOTTOM_THRESHOLD);
  }, [scrollToBottom]);

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
    };
  }, [followLive, followIfAuto]);

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
