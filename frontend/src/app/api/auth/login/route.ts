import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { id: string; email: string; role: "admin" | "staff" };
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body: unknown = await request.json().catch(() => null);
  if (!body) return NextResponse.json({ error: { message: "Invalid request" } }, { status: 400 });

  const upstream = await fetch(`${API}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  }).catch(() => null);
  if (!upstream) {
    return NextResponse.json({ error: { message: "The server is unreachable" } }, { status: 502 });
  }
  const data: unknown = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });

  const login = data as LoginResponse;
  const response = NextResponse.json({
    access_token: login.access_token,
    expires_in: login.expires_in,
    user: login.user,
  });
  // The refresh token never reaches JavaScript: HttpOnly cookie scoped to the auth routes.
  response.cookies.set("refresh_token", login.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/api/auth",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}
