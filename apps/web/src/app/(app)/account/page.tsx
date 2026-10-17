"use client";

import { LogOut } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

export default function AccountPage() {
  const { user, logout } = useAuth();

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Account" description="Your profile and session." />
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-xl space-y-4">
          <Card>
            <CardTitle>Profile</CardTitle>
            <dl className="mt-4 space-y-3 text-sm">
              <Row label="Display name" value={user?.display_name || "—"} />
              <Row label="Email" value={user?.email ?? "—"} />
              <Row
                label="Member since"
                value={user ? formatDate(user.created_at) : "—"}
              />
            </dl>
            <CardDescription>
              Profile editing is not wired to the API yet, so nothing here is editable.
            </CardDescription>
          </Card>

          <Card>
            <CardTitle>Session</CardTitle>
            <CardDescription>
              You are signed in with a JWT session held in an httpOnly cookie. Signing out
              clears it on this device.
            </CardDescription>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => void logout()}
            >
              <LogOut className="h-4 w-4" /> Sign out
            </Button>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/40 pb-2">
      <dt className="text-muted">{label}</dt>
      <dd className="text-slate-100">{value}</dd>
    </div>
  );
}
