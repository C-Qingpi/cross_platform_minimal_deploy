import { useCallback, useRef, useState } from "react";

const BOTTOM_THRESHOLD = 80;

/** Pin to bottom until the user scrolls up; re-pin when they return to the bottom. */
export function useScrollPin(threshold = BOTTOM_THRESHOLD) {
  const pinnedRef = useRef(true);
  const [isPinned, setIsPinned] = useState(true);
  const userScrollingRef = useRef(false);

  const setPinned = useCallback((pinned: boolean) => {
    pinnedRef.current = pinned;
    setIsPinned(pinned);
  }, []);

  const detach = useCallback(() => {
    userScrollingRef.current = true;
    setPinned(false);
  }, [setPinned]);

  const attach = useCallback(() => {
    userScrollingRef.current = false;
    setPinned(true);
  }, [setPinned]);

  const scrollToBottom = useCallback((el: HTMLElement, behavior: ScrollBehavior = "auto") => {
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  const onScroll = useCallback(
    (el: HTMLElement) => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = dist <= threshold;

      if (userScrollingRef.current) {
        if (atBottom) userScrollingRef.current = false;
        else {
          pinnedRef.current = false;
          setIsPinned(false);
          return;
        }
      }

      pinnedRef.current = atBottom;
      setIsPinned(atBottom);
    },
    [threshold],
  );

  return {
    pinnedRef,
    isPinned,
    attach,
    detach,
    scrollToBottom,
    onScroll,
  };
}
