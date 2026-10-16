"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import type { Page, Ticket, TicketDetail } from "@/lib/types";

const FILTERS = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "", label: "All" },
] as const;

export default function HandoffsPage() {
  const [filter, setFilter] = useState<string>("open");
  const [selected, setSelected] = useState<string | null>(null);

  const list = usePolling(
    () => api<Page<Ticket>>(`/api/v1/handoffs?page_size=50${filter ? `&status=${filter}` : ""}`),
    5000,
    [filter],
  );

  return (
    <div>
      <h1 className="anim-fade-up text-2xl font-semibold">Handoff inbox</h1>
      <p className="anim-fade-up d1 mt-1 text-sm text-stone-500">Conversations the AI passed to a human. Replies appear instantly in the guest&apos;s chat.</p>

      <div role="tablist" aria-label="Ticket status" className="anim-fade-up d2 mt-5 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            type="button"
            role="tab"
            aria-selected={filter === f.value}
            onClick={() => {
              setFilter(f.value);
              setSelected(null);
            }}
            className={`rounded-full px-4 py-1.5 text-sm transition-all duration-200 hover:-translate-y-px active:scale-95 ${filter === f.value ? "bg-brand text-white shadow-md shadow-brand/20" : "bg-white text-stone-700 border border-stone-300 hover:bg-stone-100"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[340px_1fr]">
        <ul className="space-y-2" aria-label="Tickets">
          {list.data?.items.length === 0 && <li className="anim-fade-up rounded-xl border border-stone-200 bg-white p-6 text-center text-sm text-stone-500">Nothing here. 🎉</li>}
          {list.data?.items.map((t, i) => (
            <li key={t.id} className="anim-fade-up" style={{ animationDelay: `${Math.min(i * 60, 360)}ms` }}>
              <button
                type="button"
                onClick={() => setSelected(t.id)}
                aria-current={selected === t.id}
                className={`w-full rounded-xl border bg-white p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-brand hover:shadow-md ${selected === t.id ? "border-brand ring-1 ring-brand" : "border-stone-200"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold">{t.ref}</span>
                  <StatusBadge status={t.status} />
                </div>
                <p className="mt-1 text-sm text-stone-700">{humanize(t.reason)}</p>
                <p className="mt-1 text-xs text-stone-500">
                  {t.guest_language === "ne" ? "नेपाली" : "English"} · {formatDateTime(t.created_at)}
                </p>
              </button>
            </li>
          ))}
        </ul>

        {selected ? <TicketPanel key={selected} ticketId={selected} onChanged={() => void list.reload()} /> : (
          <div className="anim-fade-in rounded-2xl border border-dashed border-stone-300 p-10 text-center text-stone-500">Select a ticket to read the conversation and reply.</div>
        )}
      </div>
    </div>
  );
}

function TicketPanel({ ticketId, onChanged }: { ticketId: string; onChanged: () => void }) {
  const detail = usePolling(() => api<TicketDetail>(`/api/v1/handoffs/${ticketId}`), 4000);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ticket = detail.data;
  const closed = ticket?.status === "resolved";

  const reply = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/handoffs/${ticketId}/reply`, { method: "POST", json: { text: text.trim() } });
      setText("");
      await detail.reload();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send");
    } finally {
      setBusy(false);
    }
  };

  const resolve = async () => {
    if (!window.confirm("Close this ticket and hand the chat back to the AI?")) return;
    setBusy(true);
    try {
      await api(`/api/v1/handoffs/${ticketId}/resolve`, { method: "POST" });
      await detail.reload();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resolve");
    } finally {
      setBusy(false);
    }
  };

  if (!ticket) return <div className="anim-fade-in rounded-2xl border border-stone-200 bg-white p-8 text-stone-500">Loading…</div>;

  return (
    <section className="anim-scale-in flex max-h-[75vh] flex-col rounded-2xl border border-stone-200 bg-white" aria-label={`Ticket ${ticket.ref}`}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-200 px-5 py-3">
        <div>
          <h2 className="font-mono text-base font-semibold">{ticket.ref}</h2>
          <p className="text-xs text-stone-500">{humanize(ticket.reason)} · {ticket.guest_language === "ne" ? "Guest writes Nepali" : "Guest writes English"}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={ticket.status} />
          {!closed && <Button variant="secondary" className="px-3 py-1.5 text-xs" disabled={busy} onClick={() => void resolve()}>Resolve</Button>}
        </div>
      </header>
      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto bg-paper px-5 py-4">
        {ticket.messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "anim-slide-in-left border border-stone-200 bg-white" : "anim-slide-in-right " + (m.role === "human_agent" ? "bg-gold-soft border border-gold" : "bg-stone-200/70")}`}>
              <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500">{m.role === "user" ? "Guest" : m.role === "human_agent" ? "Team" : "AI"}</p>
              <p className="whitespace-pre-wrap break-words">{m.content}</p>
            </div>
          </div>
        ))}
      </div>
      {error && <p role="alert" className="anim-shake mx-5 mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <form onSubmit={reply} className="flex gap-2 border-t border-stone-200 p-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={2000}
          disabled={closed}
          placeholder={closed ? "Ticket resolved" : ticket.guest_language === "ne" ? "नेपालीमा जवाफ लेख्नुहोस्…" : "Write a reply to the guest…"}
          aria-label="Reply to the guest"
          className="flex-1 resize-none rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:bg-stone-100"
        />
        <Button type="submit" disabled={busy || closed || !text.trim()}>Send</Button>
      </form>
    </section>
  );
}
