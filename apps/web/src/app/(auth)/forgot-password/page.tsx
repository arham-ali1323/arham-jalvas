"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { auth } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="We'll email you a link if an account exists for that address."
      footer={
        <Link href="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <p className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary-soft">
          If an account exists for {email}, a reset link is on its way. The link expires in
          30 minutes.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? <Spinner /> : null}
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
