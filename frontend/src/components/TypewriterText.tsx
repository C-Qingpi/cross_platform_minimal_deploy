import { useEffect, useMemo, useRef, useState } from "react";
import MarkdownPreview from "@uiw/react-markdown-preview";
import type { Components } from "react-markdown";

const TICK_MS = 10;
const TARGET_DURATION_MS = 450;
const MIN_CHARS_PER_TICK = 8;
const MAX_CHARS_PER_TICK = 200;

function paceForLength(len: number): number {
  if (len <= 0) return 1;
  const ticks = Math.max(12, Math.ceil(TARGET_DURATION_MS / TICK_MS));
  return Math.min(MAX_CHARS_PER_TICK, Math.max(MIN_CHARS_PER_TICK, Math.ceil(len / ticks)));
}

interface TypewriterTextProps {
  text: string;
  animate: boolean;
  messageId?: string;
  onComplete?: () => void;
  className?: string;
  markdown?: boolean;
}

export function TypewriterText({
  text,
  animate,
  messageId = "",
  onComplete,
  className = "",
  markdown = true,
}: TypewriterTextProps) {
  const [visible, setVisible] = useState(animate ? 0 : text.length);
  const completedRef = useRef(false);
  const runIdRef = useRef("");
  const textLenRef = useRef(text.length);
  textLenRef.current = text.length;
  const charsPerTick = useMemo(() => paceForLength(text.length), [text.length]);

  useEffect(() => {
    if (!animate) {
      setVisible(text.length);
      return;
    }

    const runId = messageId || text.slice(0, 32);
    if (runIdRef.current === runId) return;
    runIdRef.current = runId;
    completedRef.current = false;
    setVisible(0);

    let i = 0;
    const id = window.setInterval(() => {
      i = Math.min(textLenRef.current, i + charsPerTick);
      setVisible(i);
      if (i >= textLenRef.current) {
        window.clearInterval(id);
        if (!completedRef.current) {
          completedRef.current = true;
          onComplete?.();
        }
      }
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [animate, messageId, onComplete, charsPerTick]);

  useEffect(() => {
    if (animate) return;
    setVisible(text.length);
    runIdRef.current = "";
  }, [animate, text.length, text]);

  const components = useMemo<Components>(
    () => ({
      table: ({ children, ...props }) => (
        <div className="md-table-wrap">
          <table {...props}>{children}</table>
        </div>
      ),
    }),
    [],
  );

  const slice = text.slice(0, visible);
  const done = visible >= text.length;

  if (!markdown || !done) {
    return (
      <span className={`whitespace-pre-wrap ${className}`}>
        {slice}
        {animate && !done && (
          <span className="inline-block w-0.5 h-3.5 ml-0.5 bg-indigo-400/80 animate-pulse align-middle" />
        )}
      </span>
    );
  }

  return (
    <div className={className} data-color-mode="light">
      <MarkdownPreview
        source={text}
        components={components}
        wrapperElement={{ "data-color-mode": "light" }}
      />
    </div>
  );
}
