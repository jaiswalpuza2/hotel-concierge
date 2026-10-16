"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth";

const links = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/handoffs", label: "Handoff inbox" },
  { href: "/admin/documents", label: "Knowledge base" },
  { href: "/admin/conversations", label: "Conversations" },
  { href: "/admin/bookings", label: "Bookings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex w-full flex-col gap-1 border-b border-stone-200 bg-white p-4 md:min-h-screen md:w-60 md:border-b-0 md:border-r">
      <p className="mb-3 text-sm font-semibold text-brand">Himalayan Heritage</p>
      <nav aria-label="Admin" className="flex gap-1 overflow-x-auto md:flex-col">
        {links.map((l) => {
          const active = l.href === "/admin" ? pathname === "/admin" : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 hover:translate-x-0.5 ${
                active ? "bg-brand-soft text-brand shadow-sm" : "text-stone-600 hover:bg-stone-100"
              }`}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-4 border-t border-stone-200 pt-4 md:mt-auto">
        <p className="mb-2 truncate text-xs text-stone-500">
          {user?.email || "Signed in"} · {user?.role}
        </p>
        <div className="flex gap-2">
          <Link href="/chat" className="rounded-lg border border-stone-300 px-3 py-2 text-xs hover:bg-stone-100">
            Open chat
          </Link>
          <Button variant="secondary" className="px-3 py-2 text-xs" onClick={() => void logout()}>
            Sign out
          </Button>
        </div>
      </div>
    </aside>
  );
}
