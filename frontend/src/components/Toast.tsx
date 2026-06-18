export function Toast({ toast }: { toast: { message: string } | null }) {
  if (!toast) return null;
  return (
    <div className="fixed bottom-20 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-slate-200 bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
      {toast.message}
    </div>
  );
}
