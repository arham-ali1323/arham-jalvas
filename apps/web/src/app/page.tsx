import Link from "next/link";
import { ArrowRight, Cpu, Mic, ShieldCheck, Sparkles } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const features = [
  {
    icon: Sparkles,
    title: "Streaming chat",
    body: "Token-by-token responses with conversation memory that follows you across devices.",
  },
  {
    icon: Mic,
    title: "Live voice",
    body: "Real-time speech with interruption handling and an animated state visualizer.",
  },
  {
    icon: Cpu,
    title: "Desktop companion",
    body: "Pair your desktop with explicit, scoped permissions and a full action history.",
  },
  {
    icon: ShieldCheck,
    title: "Security first",
    body: "Argon2id passwords, JWT sessions, and tokens held in httpOnly cookies.",
  },
];

export default function LandingPage() {
  const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "MARK LIV";

  return (
    <main className="relative mx-auto flex min-h-screen w-full min-w-0 max-w-6xl flex-col px-6">
      <header className="flex items-center justify-between py-6">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg border border-primary/40 bg-primary/10 text-primary shadow-glow-sm">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold tracking-[0.25em] text-slate-100">
            {appName}
          </span>
        </div>
        <nav className="flex items-center gap-2">
          <Link href="/login" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
            Sign in
          </Link>
          <Link href="/register" className={cn(buttonVariants({ size: "sm" }))}>
            Get started
          </Link>
        </nav>
      </header>

      <section className="flex flex-1 flex-col items-center justify-center py-16 text-center">
        <span className="animate-pulse-glow rounded-full border border-primary/30 bg-primary/10 px-4 py-1 text-xs uppercase tracking-[0.3em] text-primary-soft">
          AI Platform
        </span>
        <h1 className="mt-6 max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-6xl">
          Your intelligent <span className="text-primary text-glow">assistant</span>, on the
          web and on your desk.
        </h1>
        <p className="mt-5 max-w-2xl text-base text-slate-300 sm:text-lg">
          One account connects a fast, elegant web experience with a desktop companion you
          explicitly authorize. Built for real work, not demos.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link href="/register" className={cn(buttonVariants({ size: "lg" }))}>
            Create your account <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/login"
            className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
          >
            I already have one
          </Link>
        </div>
      </section>

      <section className="grid gap-4 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {features.map((feature) => (
          <div
            key={feature.title}
            className="glass animate-fade-up rounded-2xl p-5 transition-colors hover:border-primary/40"
          >
            <feature.icon className="h-5 w-5 text-primary" />
            <h2 className="mt-3 text-sm font-semibold text-slate-100">{feature.title}</h2>
            <p className="mt-1 text-sm text-muted">{feature.body}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-border/60 py-6 text-center text-xs text-muted">
        {appName} — build status is verifiable; no feature is claimed until it works.
      </footer>
    </main>
  );
}
