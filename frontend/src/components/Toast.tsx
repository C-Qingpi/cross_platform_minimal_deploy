import { useEffect, useRef, useState } from "react";
import type { ToastState } from "../types/api";

export function Toast({ toast }: { toast: ToastState | null }) {
  const [leaving, setLeaving] = useState(false);
  const [visible, setVisible] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!toast) {
      setVisible(false);
      setLeaving(false);
      return;
    }

    // Reset state for new toast
    setVisible(false);
    setLeaving(false);

    // Trigger entrance animation on next frame
    const enterFrame = requestAnimationFrame(() => {
      setVisible(true);
    });

    // Start progress bar animation
    const progressEl = progressRef.current;
    if (progressEl) {
      progressEl.style.transition = "none";
      progressEl.style.width = "100%";
      // Force reflow
      void progressEl.offsetWidth;
      progressEl.style.transition = `width ${toast.ms}ms linear`;
      progressEl.style.width = "0%";
    }

    // Schedule exit animation (start slightly before unmount)
    const leaveDelay = toast.ms - 300;
    timerRef.current = setTimeout(() => {
      setLeaving(true);
    }, Math.max(leaveDelay, 0));

    return () => {
      cancelAnimationFrame(enterFrame);
      clearTimeout(timerRef.current);
    };
  }, [toast]);

  if (!toast && !visible) return null;

  return (
    <div
      className={`fixed bottom-20 left-1/2 z-50 -translate-x-1/2
        rounded-xl border border-white/15 bg-gradient-to-br from-slate-800/95 via-slate-900/95 to-slate-950/95
        px-5 py-3 text-sm text-white shadow-2xl backdrop-blur-md
        shadow-black/30
        transition-all duration-300 ease-out
        ${visible && !leaving
          ? "translate-y-0 opacity-100 scale-100"
          : "translate-y-4 opacity-0 scale-95"
        }`}
    >
      <div className="flex items-center gap-2.5">
        {/* Status dot */}
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>

        <span className="leading-snug">{toast?.message ?? ""}</span>
      </div>

      {/* Progress bar */}
      <div className="mt-2 h-0.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          ref={progressRef}
          className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-300"
          style={{ width: "100%" }}
        />
      </div>
    </div>
  );
}
