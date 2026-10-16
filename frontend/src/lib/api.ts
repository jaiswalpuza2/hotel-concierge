import { API_URL } from "./config";

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

interface RefreshResponse {
  access_token: string;
  expires_in: number;
}

/** Ask the Next.js BFF (which holds the HttpOnly refresh cookie) for a new access token. */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
        if (!res.ok) return null;
        const data = (await res.json()) as RefreshResponse;
        accessToken = data.access_token;
        return accessToken;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string } };
    return new ApiError(res.status, body.error?.code ?? "http_error", body.error?.message ?? res.statusText);
  } catch {
    return new ApiError(res.status, "http_error", res.statusText || "Request failed");
  }
}

interface ApiOptions extends Omit<RequestInit, "body"> {
  /** Attach the staff access token (default true). Guest chat endpoints pass false. */
  auth?: boolean;
  json?: unknown;
  body?: BodyInit | null;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { auth = true, json, headers, body, ...rest } = options;

  const send = async (token: string | null): Promise<Response> => {
    const h = new Headers(headers);
    if (json !== undefined) h.set("Content-Type", "application/json");
    if (auth && token) h.set("Authorization", `Bearer ${token}`);
    return fetch(`${API_URL}${path}`, {
      ...rest,
      headers: h,
      body: json !== undefined ? JSON.stringify(json) : body,
    });
  };

  let res = await send(accessToken);
  if (res.status === 401 && auth) {
    const fresh = await refreshAccessToken();
    if (fresh) res = await send(fresh);
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
