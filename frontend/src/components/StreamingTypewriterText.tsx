import { useEffect, useRef, useState } from "react";

/** Max time visible text may lag behind the latest stream target. */
const MAX_TAIL_LAG_SEC = 0.5;
const FINISH_LAG_SEC = 0.05;

interface StreamingTypewriterTextProps {
  text: string;
  live: boolean;
  /** Explicit reset only (e.g. new turn). Do not tie to poll timestamps. */
  sessionKey?: string;
  className?: string;
  cursorClassName?: string;
  /** Fired when visible length changes during live reveal (for scroll follow). */
  onReveal?: () => void;
}

export function StreamingTypewriterText({
  text,
  live,
  sessionKey = "",
  className = "",
  cursorClassName = "bg-amber-500",
  onReveal,
}: StreamingTypewriterTextProps) {
  const [visible, setVisible] = useState(0);
  const targetRef = useRef(text);
  const prevTargetRef = useRef("");
  const visibleRef = useRef(0);
  const sessionRef = useRef(sessionKey);
  const liveRef = useRef(live);
  const onRevealRef = useRef(onReveal);

  liveRef.current = live;
  onRevealRef.current = onReveal;

  useEffect(() => {
    if (sessionKey !== sessionRef.current) {
      sessionRef.current = sessionKey;
      visibleRef.current = 0;
      prevTargetRef.current = "";
      setVisible(0);
    }
  }, [sessionKey]);

  useEffect(() => {
    const prev = prevTargetRef.current;
    targetRef.current = text;

    if (!text) {
      visibleRef.current = 0;
      prevTargetRef.current = "";
      setVisible(0);
      return;
    }

    if (!prev) {
      prevTargetRef.current = text;
      return;
    }

    if (text.startsWith(prev)) {
      const committed = prev.length;
      if (visibleRef.current < committed) {
        visibleRef.current = committed;
        setVisible(committed);
        if (liveRef.current) onRevealRef.current?.();
      }
      prevTargetRef.current = text;
      return;
    }

    visibleRef.current = 0;
    prevTargetRef.current = text;
    setVisible(0);
  }, [text]);

  useEffect(() => {
    let raf = 0;
    let lastTs = performance.now();

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - lastTs) / 1000);
      lastTs = now;

      const targetLen = targetRef.current.length;
      let v = visibleRef.current;
      const isLive = liveRef.current;

      if (v < targetLen) {
        const lag = targetLen - v;
        const budgetSec = isLive ? MAX_TAIL_LAG_SEC : FINISH_LAG_SEC;
        const speed = lag / budgetSec;
        v = Math.min(targetLen, v + Math.max(1, speed * dt));
        visibleRef.current = v;
        setVisible(v);
        if (isLive) onRevealRef.current?.();
      }

      if (isLive || v < targetRef.current.length) {
        raf = requestAnimationFrame(tick);
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [sessionKey, live]);

  const slice = text.slice(0, visible);
  const showCursor = live || visible < text.length;

  return (
    <span className={`whitespace-pre-wrap ${className}`}>
      {slice}
      {showCursor && (
        <span
          className={`ml-0.5 inline-block h-3.5 w-0.5 animate-pulse align-middle ${cursorClassName}`}
        />
      )}
    </span>
  );
}
