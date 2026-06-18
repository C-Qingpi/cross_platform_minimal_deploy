import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";

interface DirectoryBrowserProps {
  value: string;
  onChange: (path: string) => void;
  label?: string;
}

export function DirectoryBrowser({ value, onChange, label = "Folder" }: DirectoryBrowserProps) {
  const [currentPath, setCurrentPath] = useState(value);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<api.FsEntry[]>([]);
  const [roots, setRoots] = useState<api.FsRoot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const initialized = useRef(false);

  const loadBrowse = useCallback(async (path: string, select = false) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.browseDirectory(path);
      setCurrentPath(data.path);
      setParent(data.parent);
      setEntries(data.entries);
      if (select) onChange(data.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to browse");
    } finally {
      setLoading(false);
    }
  }, [onChange]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    api.fetchFsRoots().then((r) => {
      setRoots(r);
      const start = value || r[0]?.path;
      if (start) loadBrowse(start, Boolean(value));
    });
  }, [value, loadBrowse]);

  useEffect(() => {
    if (value && value !== currentPath) {
      loadBrowse(value, true);
    }
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        {loading && <span className="text-xs text-slate-400">Loading…</span>}
      </div>

      <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-slate-100">
        {roots.map((r) => (
          <button
            key={r.path}
            type="button"
            onClick={() => loadBrowse(r.path, true)}
            className="rounded px-2 py-0.5 text-xs bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-700"
          >
            {r.name}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 bg-white">
        <button
          type="button"
          disabled={!parent}
          onClick={() => parent && loadBrowse(parent, true)}
          className="shrink-0 rounded px-2 py-1 text-xs border border-slate-200 disabled:opacity-30 hover:bg-slate-50"
        >
          Up
        </button>
        <input
          readOnly
          value={currentPath}
          className="flex-1 min-w-0 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-mono text-slate-700"
        />
        <button
          type="button"
          onClick={() => onChange(currentPath)}
          className="shrink-0 rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
        >
          Select
        </button>
      </div>

      {error && <div className="px-3 py-2 text-xs text-red-600">{error}</div>}

      <ul className="max-h-48 overflow-y-auto py-1">
        {entries.map((entry) => (
          <li key={entry.path}>
            <button
              type="button"
              onClick={() => loadBrowse(entry.path, true)}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-indigo-50"
            >
              <span className="text-slate-400 text-xs font-mono shrink-0">dir</span>
              <span className="truncate">{entry.name}</span>
            </button>
          </li>
        ))}
        {!loading && entries.length === 0 && (
          <li className="px-3 py-4 text-center text-xs text-slate-400">No subfolders</li>
        )}
      </ul>
    </div>
  );
}
