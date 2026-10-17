import { NextResponse } from "next/server";

import { applyTokenCookies, backendBase, getAccessToken } from "@/lib/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const { token, minted } = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated." }, { status: 401 });
  }

  const upstream = await fetch(`${backendBase()}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const res = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
  if (minted) applyTokenCookies(res, minted);
  return res;
}
