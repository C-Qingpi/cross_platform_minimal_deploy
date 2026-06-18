import type { ReactNode } from "react";

interface SidebarPanelProps {
  title: string;
  expanded: boolean;
  onToggleExpand: () => void;
  actions?: ReactNode;
  children: ReactNode;
  collapsed?: boolean;
}

export function SidebarPanel({
  title,
  expanded,
  onToggleExpand,
  actions,
  children,
  collapsed = false,
}: SidebarPanelProps) {
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={onToggleExpand}
        className="shrink-0 border-b border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hover:bg-slate-50 w-full"
      >
        {title} ›
      </button>
    );
  }

  return (
    <div
      className={`flex flex-col min-h-0 border-b border-slate-200 ${
        expanded ? "flex-1" : "shrink-0 max-h-[45%]"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 bg-slate-50/80">
        <button
          type="button"
          onClick={onToggleExpand}
          className="text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-800"
          title={expanded ? "Collapse panel" : "Expand panel"}
        >
          {title} {expanded ? "▾" : "▸"}
        </button>
        {actions && <div className="ml-auto flex gap-1">{actions}</div>}
      </div>
      <div className="flex-1 overflow-y-auto p-2 min-h-0">{children}</div>
    </div>
  );
}
