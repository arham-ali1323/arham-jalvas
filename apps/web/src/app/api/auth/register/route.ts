import { NextResponse } from "next/server";

import { applyTokenCookies, backendBase, forwardError } from "@/lib/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body) {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }

  const upstream = await fetch(`${backendBase()}/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!upstream.ok) return forwardError(upstream);

  const tokens = (await upstream.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  const me = await fetch(`${backendBase()}/auth/me`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
    cache: "no-store",
  });

  const res = NextResponse.json({ user: await me.json() }, { status: 201 });
  return applyTokenCookies(res, {
    access: tokens.access_token,
    refresh: tokens.refresh_token,
    expiresIn: tokens.expires_in,
  });
}
