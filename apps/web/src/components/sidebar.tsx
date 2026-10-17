"use client";

import {
  LogOut,
  MessagesSquare,
  Mic,
  MonitorSmartphone,
  Plus,
  Settings,
  Sparkles,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAppState } from "@/components/app-state-provider";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/chat", label: "Chat", icon: MessagesSquare },
  { href: "/voice", label: "Voice", icon: Mic },
  { href: "/devices", label: "Devices", icon: MonitorSmartphone },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/account", label: "Account", icon: UserRound },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { setActiveConversationId } = useAppState();
  const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "MARK LIV";

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-border/60 bg-surface/40">
      <div className="p-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-primary/40 bg-primary/10 text-primary shadow-glow-sm">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-xs font-semibold tracking-[0.25em] text-slate-100">
            {appName}
          </span>
        </Link>
        <Button
          className="mt-4 w-full"
          onClick={() => {
            setActiveConversationId(null);
            router.push("/chat");
          }}
        >
          <Plus className="h-4 w-4" /> New chat
        </Button>
      </div>

      <nav className="flex-1 space-y-1 px-2">
        {nav.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary-soft shadow-glow-sm"
                  : "text-slate-300 hover:bg-surface-2 hover:text-white",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border/60 p-4">
        <p className="truncate text-sm text-slate-200">
          {user?.display_name || user?.email}
        </p>
        <p className="truncate text-xs text-muted">{user?.email}</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3 w-full justify-start"
          onClick={() => void logout()}
        >
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </div>
    </aside>
  );
}
