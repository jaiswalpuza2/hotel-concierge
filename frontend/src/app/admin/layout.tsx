"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/admin/Sidebar";
import { AuthProvider, useAuth } from "@/lib/auth";

function Guard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const onLogin = pathname === "/admin/login";

  useEffect(() => {
    if (loading) return;
    if (!user && !onLogin) router.replace("/admin/login");
    if (user && onLogin) router.replace("/admin");
  }, [loading, user, onLogin, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-stone-500" role="status">
        <span className="h-7 w-7 animate-spin rounded-full border-2 border-brand border-t-transparent" aria-hidden="true" />
        Loading…
      </div>
    );
  }
  if (onLogin) return <>{children}</>;
  if (!user) return null;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar />
      <div className="flex-1 overflow-x-hidden p-4 sm:p-8">{children}</div>
    </div>
  );
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  // Auth (and its silent token refresh) only runs for staff pages, never for guest chat.
  return (
    <AuthProvider>
      <Guard>{children}</Guard>
    </AuthProvider>
  );
}
