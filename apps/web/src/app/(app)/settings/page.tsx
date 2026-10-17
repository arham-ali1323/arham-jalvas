"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { chat } from "@/lib/api";
import type { ProviderInfo } from "@/lib/types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    chat
      .providers()
      .then(setProviders)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load."));
  }, []);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" description="Model, appearance, and device defaults." />
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-xl space-y-4">
          <Card>
            <CardTitle>AI model</CardTitle>
            {error ? (
              <CardDescription>{error}</CardDescription>
            ) : providers === null ? (
              <Spinner className="mt-4" />
            ) : (
              <div className="mt-4 space-y-2 text-sm">
                {providers.map((provider) => (
                  <div
                    key={provider.name}
                    className="flex items-center justify-between border-b border-border/40 pb-2"
                  >
                    <span className="capitalize text-slate-100">{provider.name}</span>
                    <span
                      className={
                        provider.configured ? "text-success" : "text-danger"
                      }
                    >
                      {provider.configured ? provider.model : "not configured"}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <CardDescription>
              The active provider is chosen by the backend from server-side environment
              variables — no API keys ever reach the browser.
            </CardDescription>
          </Card>

          <Card>
            <CardTitle>Appearance</CardTitle>
            <CardDescription>
              MARK LIV uses a dark, high-contrast theme optimised for long sessions. Theme
              switching and density controls are planned.
            </CardDescription>
          </Card>

          <Card>
            <CardTitle>Voice &amp; devices</CardTitle>
            <CardDescription>
              Microphone, speaker, and voice preferences are configured in the Voice section
              once live voice ships. Nothing is faked here.
            </CardDescription>
          </Card>
        </div>
      </div>
    </div>
  );
}
