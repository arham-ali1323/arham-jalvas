import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Tokens are held in httpOnly cookies and NEVER exposed to client JavaScript,
 * so an XSS bug cannot exfiltrate them. All backend traffic is proxied through
 * Next route handlers that attach the bearer header server-side.
 */
export const ACCESS_COOKIE = "ml_access";
export const REFRESH_COOKIE = "ml_refresh";
const REFRESH_MAX_AGE = 60 * 60 * 24 * 30; // 30 days
const IS_PROD = process.env.NODE_ENV === "production";

export interface TokenPair {
  access: string;
  refresh: string;
  expiresIn: number;
}

export function backendBase(): string {
  const configured = process.env.API_BASE_URL?.trim();
  if (!configured && IS_PROD) {
    throw new Error("API_BASE_URL must be set in production.");
  }
  return (configured ?? "http://localhost:8080").replace(/\/+$/, "");
}

function decodePayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    return JSON.parse(Buffer.from(part, "base64url").toString("utf8"));
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string, skewSeconds = 20): boolean {
  const payload = decodePayload(token);
  const exp = typeof payload?.exp === "number" ? payload.exp : null;
  if (exp === null) return true;
  return Date.now() / 1000 >= exp - skewSeconds;
}

async function refreshTokens(refresh: string): Promise<TokenPair | null> {
  try {
    const res = await fetch(`${backendBase()}/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      access_token: string;
      refresh_token: string;
      expires_in: number;
    };
    return { access: data.access_token, refresh: data.refresh_token, expiresIn: data.expires_in };
  } catch {
    return null;
  }
}

/**
 * Returns a usable access token, transparently refreshing if the access token
 * is missing/expired and a refresh token is present. `minted` is non-null when
 * new cookies must be written onto the outgoing response.
 */
export async function getAccessToken(): Promise<{ token: string | null; minted: TokenPair | null }> {
  const jar = await cookies();
  const access = jar.get(ACCESS_COOKIE)?.value;
  if (access && !isTokenExpired(access)) {
    return { token: access, minted: null };
  }
  const refresh = jar.get(REFRESH_COOKIE)?.value;
  if (refresh) {
    const minted = await refreshTokens(refresh);
    if (minted) return { token: minted.access, minted };
  }
  return { token: null, minted: null };
}

export function applyTokenCookies(res: NextResponse, tokens: TokenPair): NextResponse {
  res.cookies.set(ACCESS_COOKIE, tokens.access, {
    httpOnly: true,
    sameSite: "lax",
    secure: IS_PROD,
    path: "/",
    maxAge: Math.max(60, tokens.expiresIn),
  });
  res.cookies.set(REFRESH_COOKIE, tokens.refresh, {
    httpOnly: true,
    sameSite: "lax",
    secure: IS_PROD,
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
  return res;
}

export function clearTokenCookies(res: NextResponse): NextResponse {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    res.cookies.set(name, "", {
      httpOnly: true,
      sameSite: "lax",
      secure: IS_PROD,
      path: "/",
      maxAge: 0,
    });
  }
  return res;
}

export async function forwardError(upstream: Response): Promise<NextResponse> {
  const text = await upstream.text();
  let detail = "Request failed.";
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") detail = parsed.detail;
  } catch {
    if (text) detail = text;
  }
  return NextResponse.json({ detail }, { status: upstream.status });
}

export async function forwardPublicAuthPost(
  request: Request,
  backendPath: string,
): Promise<NextResponse> {
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }

  const upstream = await fetch(`${backendBase()}${backendPath}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!upstream.ok) return forwardError(upstream);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
