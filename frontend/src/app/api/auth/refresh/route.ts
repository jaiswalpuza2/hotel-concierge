import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get("refresh_token")?.value;
  if (!token) return NextResponse.json({ error: { message: "Not signed in" } }, { status: 401 });

  const upstream = await fetch(`${API}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
    cache: "no-store",
  }).catch(() => null);
  if (!upstream) {
    return NextResponse.json({ error: { message: "The server is unreachable" } }, { status: 502 });
  }
  const data: unknown = await upstream.json().catch(() => ({}));
  const response = NextResponse.json(data, { status: upstream.status });
  if (upstream.status === 401) response.cookies.delete({ name: "refresh_token", path: "/api/auth" });
  return response;
}
