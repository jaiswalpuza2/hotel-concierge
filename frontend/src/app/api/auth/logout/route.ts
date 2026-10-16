import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get("refresh_token")?.value;
  if (token) {
    await fetch(`${API}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
      cache: "no-store",
    }).catch(() => null);
  }
  const response = new NextResponse(null, { status: 204 });
  response.cookies.delete({ name: "refresh_token", path: "/api/auth" });
  return response;
}
