import { useEffect, useState } from "react";
import { DirectoryBrowser } from "./DirectoryBrowser";
import * as api from "../lib/api";

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (agentId: string) => void;
}

export function CreateAgentModal({
  open,
  onClose,
  onCreated,
}: CreateAgentModalProps) {
  const [agentId, setAgentId] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [mountPath, setMountPath] = useState("");
  const [mountName, setMountName] = useState("extra");
  const [showMountBrowser, setShowMountBrowser] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setAgentId("");
    setWorkspace("");
    setMountPath("");
    setMountName("extra");
    setShowMountBrowser(false);
    setError("");
    api.fetchFsRoots().then((roots) => {
      const deploy = roots.find((r) => r.name === "Deploy workspaces");
      if (deploy) setWorkspace(deploy.path);
    });
  }, [open]);

  useEffect(() => {
    if (!open || !agentId.trim()) return;
    const id = agentId.trim();
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) return;
    api.fetchDefaultWorkspace(id).then(setWorkspace).catch(() => {});
  }, [agentId, open]);

  if (!open) return null;

  const idValid = /^[a-zA-Z0-9_-]+$/.test(agentId.trim());

  const handleSubmit = async () => {
    const id = agentId.trim();
    if (!idValid) {
      setError("Agent id: letters, numbers, dashes, underscores only");
      return;
    }
    if (!workspace.trim()) {
      setError("Choose a workspace folder");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const mounts =
        mountPath.trim() && mountName.trim()
          ? [{ name: mountName.trim(), path: mountPath.trim() }]
          : [];
      const result = await api.createAgent({
        agent_id: id,
        workspace: workspace.trim(),
        mounts,
      });
      if (result.error) {
        setError(result.error);
        return;
      }
      onCreated(id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">New agent</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg leading-none">
            ×
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Agent id</label>
            <input
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              placeholder="my-agent"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              autoFocus
            />
            {agentId.trim() && (
              <p className="mt-1 text-xs text-slate-400">
                Deploy default: workspaces/{agentId.trim()} (updates as you type)
              </p>
            )}
          </div>

          <DirectoryBrowser
            label="Workspace root"
            value={workspace}
            onChange={setWorkspace}
          />

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-slate-600">Extra mount (optional)</label>
              <button
                type="button"
                onClick={() => setShowMountBrowser(!showMountBrowser)}
                className="text-xs text-indigo-600 hover:underline"
              >
                {showMountBrowser ? "Hide browser" : "Browse…"}
              </button>
            </div>
            <div className="flex gap-2 mb-2">
              <input
                value={mountName}
                onChange={(e) => setMountName(e.target.value)}
                placeholder="mount name"
                className="w-28 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              />
              <input
                value={mountPath}
                onChange={(e) => setMountPath(e.target.value)}
                placeholder="Path to additional folder"
                className="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm font-mono"
              />
            </div>
            {showMountBrowser && (
              <DirectoryBrowser
                label="Mount folder"
                value={mountPath}
                onChange={setMountPath}
              />
            )}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !idValid || !workspace}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            {submitting ? "Creating…" : "Create agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
