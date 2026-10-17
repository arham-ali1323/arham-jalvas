"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { auth } from "@/lib/api";

export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token"));
    setReady(true);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await auth.confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Enter a new password for your account."
      footer={
        <Link href="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      {!ready ? (
        <Spinner />
      ) : !token ? (
        <p className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          This reset link is missing its token. Request a new link from the{" "}
          <Link href="/forgot-password" className="underline">
            forgot password
          </Link>{" "}
          page.
        </p>
      ) : done ? (
        <p className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary-soft">
          Password updated. You can now{" "}
          <Link href="/login" className="underline">
            sign in
          </Link>
          .
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? <Spinner /> : null}
            Update password
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
