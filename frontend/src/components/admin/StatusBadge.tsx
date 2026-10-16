const palette: Record<string, string> = {
  queued: "bg-stone-100 text-stone-700",
  processing: "bg-amber-100 text-amber-800",
  indexed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  open: "bg-red-100 text-red-800",
  in_progress: "bg-amber-100 text-amber-800",
  resolved: "bg-emerald-100 text-emerald-800",
  confirmed: "bg-emerald-100 text-emerald-800",
  pending: "bg-amber-100 text-amber-800",
  cancelled: "bg-stone-200 text-stone-700",
  completed: "bg-sky-100 text-sky-800",
  active: "bg-emerald-100 text-emerald-800",
  handed_off: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${palette[status] ?? "bg-stone-100 text-stone-700"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
