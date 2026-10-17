"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppStateProvider } from "@/components/app-state-provider";
import { AuthProvider, useAuth } from "@/components/auth-provider";
import { Sidebar } from "@/components/sidebar";
import { Spinner } from "@/components/ui/spinner";

function Gate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="flex items-center gap-3 text-muted">
          <Spinner /> Authenticating…
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AppStateProvider>
        <Gate>{children}</Gate>
      </AppStateProvider>
    </AuthProvider>
  );
}
