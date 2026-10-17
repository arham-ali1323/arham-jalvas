import { forwardPublicAuthPost } from "@/lib/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return forwardPublicAuthPost(request, "/auth/password-reset/confirm");
}
