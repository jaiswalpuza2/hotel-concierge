"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ConversationDetail, ConversationItem, Page } from "@/lib/types";

export default function ConversationsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const list = usePolling(() => api<Page<ConversationItem>>("/api/v1/conversations?page_size=50"), 8000);

  return (
    <div>
      <h1 className="anim-fade-up text-2xl font-semibold">Conversations</h1>
      <p className="anim-fade-up d1 mt-1 text-sm text-stone-500">Review what guests asked, which tools ran and which documents were cited.</p>
      <div className="mt-5 grid gap-5 lg:grid-cols-[340px_1fr]">
        <ul className="space-y-2" aria-label="Conversations">
          {list.data?.items.length === 0 && <li className="anim-fade-up rounded-xl border border-stone-200 bg-white p-6 text-center text-sm text-stone-500">No conversations yet.</li>}
          {list.data?.items.map((c, i) => (
            <li key={c.id} className="anim-fade-up" style={{ animationDelay: `${Math.min(i * 60, 360)}ms` }}>
              <button
                type="button"
                onClick={() => setSelected(c.id)}
                className={`w-full rounded-xl border bg-white p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-brand hover:shadow-md ${selected === c.id ? "border-brand ring-1 ring-brand" : "border-stone-200"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-stone-600">{c.session_id.slice(0, 8)}</span>
                  <StatusBadge status={c.status} />
                </div>
                <p className="mt-1 text-xs text-stone-500">
                  {c.language === "ne" ? "नेपाली" : "English"} · {formatDateTime(c.last_active_at)}
                </p>
              </button>
            </li>
          ))}
        </ul>
        {selected ? <Transcript key={selected} id={selected} /> : (
          <div className="anim-fade-in rounded-2xl border border-dashed border-stone-300 p-10 text-center text-stone-500">Select a conversation.</div>
        )}
      </div>
    </div>
  );
}

function Transcript({ id }: { id: string }) {
  const { data } = usePolling(() => api<ConversationDetail>(`/api/v1/conversations/${id}`), 6000);
  if (!data) return <div className="anim-fade-in rounded-2xl border border-stone-200 bg-white p-8 text-stone-500">Loading…</div>;
  return (
    <section className="anim-scale-in max-h-[75vh] space-y-3 overflow-y-auto rounded-2xl border border-stone-200 bg-white p-5" aria-label="Transcript">
      {data.messages.map((m, i) => (
        <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
          <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "anim-slide-in-left border border-stone-200 bg-paper" : "anim-slide-in-right " + (m.role === "human_agent" ? "border border-gold bg-gold-soft" : "bg-brand-soft")}`}>
            <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500">
              {m.role === "user" ? "Guest" : m.role === "human_agent" ? "Team" : "AI"}
              {m.intent ? ` · ${m.intent}` : ""} · {formatDateTime(m.created_at)}
            </p>
            <p className="whitespace-pre-wrap break-words">{m.content}</p>
            {m.tool_calls.length > 0 && (
              <p className="mt-1 text-xs text-stone-500">
                Tools: {m.tool_calls.map((t) => `${t.name}${t.ok ? "" : ` ✗ ${t.error_code ?? ""}`}`).join(", ")}
              </p>
            )}
            {m.sources.length > 0 && <p className="mt-1 text-xs text-stone-500">Sources: {m.sources.map((s) => s.document_name).join(", ")}</p>}
          </div>
        </div>
      ))}
    </section>
  );
}
