import { NextResponse } from "next/server";

import { clearTokenCookies } from "@/lib/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const res = new NextResponse(null, { status: 204 });
  return clearTokenCookies(res);
}
