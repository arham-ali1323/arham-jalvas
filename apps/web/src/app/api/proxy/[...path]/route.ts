import { NextResponse, type NextRequest } from "next/server";

import { applyTokenCookies, backendBase, getAccessToken } from "@/lib/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Catch-all proxy to the FastAPI backend. Injects the bearer token from the
 * httpOnly cookie (refreshing first when needed) and streams the response back
 * untouched, so SSE chat responses flow through without buffering.
 */
async function handle(request: NextRequest, path: string[]): Promise<Response> {
  const { token, minted } = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated." }, { status: 401 });
  }

  const search = new URL(request.url).search;
  const target = `${backendBase()}/${path.join("/")}${search}`;

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", request.headers.get("accept") ?? "application/json");

  const method = request.method;
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.text();

  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });

  const hasNoBody = upstream.status === 204 || upstream.status === 304;
  const res = new NextResponse(hasNoBody ? null : upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-cache",
    },
  });
  if (minted) applyTokenCookies(res, minted);
  return res;
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  return handle(request, (await ctx.params).path);
}
export async function POST(request: NextRequest, ctx: Ctx) {
  return handle(request, (await ctx.params).path);
}
export async function PUT(request: NextRequest, ctx: Ctx) {
  return handle(request, (await ctx.params).path);
}
export async function PATCH(request: NextRequest, ctx: Ctx) {
  return handle(request, (await ctx.params).path);
}
export async function DELETE(request: NextRequest, ctx: Ctx) {
  return handle(request, (await ctx.params).path);
}
