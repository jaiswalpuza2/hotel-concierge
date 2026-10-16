"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { formatNpr, humanize } from "@/lib/format";
import type { BookingItem, Page } from "@/lib/types";

const STATUSES = ["", "confirmed", "pending", "cancelled", "completed"] as const;

export default function BookingsPage() {
  const [status, setStatus] = useState<string>("");
  const [message, setMessage] = useState<string | null>(null);
  const { data, error, reload } = usePolling(
    () => api<Page<BookingItem>>(`/api/v1/bookings?page_size=50${status ? `&status=${status}` : ""}`),
    10000,
    [status],
  );

  const cancel = async (b: BookingItem) => {
    if (!window.confirm(`Cancel booking ${b.reference} for ${b.guest_name}?`)) return;
    try {
      const result = await api<{ refund_amount_npr: number; refund_percentage: number }>(`/api/v1/bookings/${b.id}/cancel`, {
        method: "POST",
        json: {},
      });
      setMessage(`${b.reference} cancelled. Refund due: ${formatNpr(result.refund_amount_npr)} (${result.refund_percentage}%).`);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not cancel");
    }
  };

  return (
    <div>
      <h1 className="anim-fade-up text-2xl font-semibold">Bookings</h1>
      <div className="anim-fade-up d1 mt-4 flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <button
            key={s || "all"}
            type="button"
            onClick={() => setStatus(s)}
            className={`rounded-full px-4 py-1.5 text-sm transition-all duration-200 hover:-translate-y-px active:scale-95 ${status === s ? "bg-brand text-white shadow-md shadow-brand/20" : "border border-stone-300 bg-white hover:bg-stone-100"}`}
          >
            {s ? humanize(s) : "All"}
          </button>
        ))}
      </div>
      {message && <p role="status" className="anim-slide-down mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{message}</p>}
      {error && <p role="alert" className="anim-shake mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="mt-5 overflow-x-auto rounded-2xl border border-stone-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3">Reference</th>
              <th className="px-4 py-3">Guest</th>
              <th className="px-4 py-3">Room</th>
              <th className="px-4 py-3">Stay</th>
              <th className="px-4 py-3">Total</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-stone-500">No bookings.</td>
              </tr>
            )}
            {data?.items.map((b, i) => (
              <tr key={b.id} className="anim-fade-up border-b border-stone-100 transition-colors duration-150 last:border-0 hover:bg-stone-50" style={{ animationDelay: `${Math.min(i * 40, 320)}ms` }}>
                <td className="px-4 py-3 font-mono text-xs font-semibold">{b.reference}</td>
                <td className="px-4 py-3">
                  {b.guest_name}
                  <p className="text-xs text-stone-500">{b.guest_phone}</p>
                </td>
                <td className="px-4 py-3">{b.room_type} · {b.room_number}</td>
                <td className="px-4 py-3 whitespace-nowrap">{b.check_in} → {b.check_out}</td>
                <td className="px-4 py-3 tabular-nums">{formatNpr(b.total_price_npr)}</td>
                <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                <td className="px-4 py-3 text-right">
                  {(b.status === "confirmed" || b.status === "pending") && (
                    <Button variant="ghost" className="px-2 py-1 text-xs text-red-600" onClick={() => void cancel(b)}>Cancel</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
