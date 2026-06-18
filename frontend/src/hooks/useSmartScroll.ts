import { useCallback, useEffect, useRef } from "react";

const BOTTOM_THRESHOLD = 80;

export function useSmartScroll(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);
  const endRef = useRef<HTMLDivElement>(null);

  const onScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinnedRef.current = dist <= BOTTOM_THRESHOLD;
  }, []);

  useEffect(() => {
    if (!pinnedRef.current) return;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { containerRef, endRef, onScroll, pinnedRef };
}
