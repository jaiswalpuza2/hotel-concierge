"use client";

import Link from "next/link";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";

function Card({ label, value, href, tone, delay }: { label: string; value: number | string; href: string; tone?: "alert"; delay?: string }) {
  const alert = tone === "alert" && Number(value) > 0;
  return (
    <Link
      href={href}
      className={`anim-fade-up rounded-2xl border bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${
        alert ? "border-red-300" : "border-stone-200"
      } ${delay ?? ""}`}
    >
      <p className="text-sm text-stone-500">{label}</p>
      {value === "–" ? (
        <div className="skeleton mt-3 h-8 w-16 rounded-lg" aria-hidden="true" />
      ) : (
        <p className={`mt-2 text-3xl font-bold tabular-nums ${alert ? "text-red-600" : "text-ink"}`}>{value}</p>
      )}
    </Link>
  );
}

export default function AdminHome() {
  const { data, error } = usePolling(() => api<Stats>("/api/v1/stats"), 10000);

  return (
    <div>
      <h1 className="anim-fade-up text-2xl font-semibold">Overview</h1>
      <p className="anim-fade-up d1 mt-1 text-sm text-stone-500">Live numbers, refreshed every 10 seconds.</p>
      {error && <p role="alert" className="anim-shake mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card label="Open handoff tickets" value={data?.open_handoffs ?? "–"} href="/admin/handoffs" tone="alert" delay="d2" />
        <Card label="Handoffs in progress" value={data?.in_progress_handoffs ?? "–"} href="/admin/handoffs" delay="d2" />
        <Card label="Arrivals today" value={data?.arrivals_today ?? "–"} href="/admin/bookings" delay="d3" />
        <Card label="Upcoming bookings" value={data?.upcoming_bookings ?? "–"} href="/admin/bookings" delay="d3" />
        <Card label="Documents indexed" value={data?.documents_indexed ?? "–"} href="/admin/documents" delay="d4" />
        <Card label="Documents failed" value={data?.documents_failed ?? "–"} href="/admin/documents" tone="alert" delay="d4" />
      </div>
    </div>
  );
}
