import Link from "next/link";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "MARK LIV";

  return (
    <main className="grid min-h-screen w-full min-w-0 place-items-center px-6">
      <div className="w-full min-w-0 max-w-md animate-fade-up">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg border border-primary/40 bg-primary/10 text-primary shadow-glow-sm">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold tracking-[0.25em] text-slate-100">
            {appName}
          </span>
        </Link>

        <div className="glass rounded-2xl p-7 shadow-panel">
          <h1 className="text-xl font-semibold text-white">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>

        {footer ? (
          <p className="mt-5 text-center text-sm text-muted">{footer}</p>
        ) : null}
      </div>
    </main>
  );
}
