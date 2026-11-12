"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";

const NAV = [
  "overview",
  "answers",
  "review",
  "expiring",
  "gaps",
  "conversations",
  "evaluation",
  "channels",
  "team",
  "settings",
  "billing",
  "audit",
] as const;

const PATH: Record<(typeof NAV)[number], string> = {
  overview: "",
  answers: "/answers",
  review: "/review",
  expiring: "/expiring",
  gaps: "/gaps",
  conversations: "/conversations",
  evaluation: "/evaluation",
  channels: "/channels",
  team: "/team",
  settings: "/settings",
  billing: "/billing",
  audit: "/audit",
};

export function Shell({
  tenantId,
  tenantName,
  accent,
  children,
}: {
  tenantId: string;
  tenantName: string;
  accent?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const m = getMessages();
  const base = `/t/${tenantId}`;

  return (
    <div
      className="min-h-screen md:grid md:grid-cols-[240px_1fr]"
      style={accent ? ({ ["--accent" as string]: accent } as React.CSSProperties) : undefined}
    >
      <aside className="border-b border-ink/10 bg-[#f3efe8]/80 md:min-h-screen md:border-b-0 md:border-r">
        <div className="px-5 py-6">
          <p className="font-display text-2xl tracking-tight text-accent">{m.brand}</p>
          <p className="mt-1 text-sm text-[var(--muted)]">{tenantName}</p>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-4 md:flex-col md:overflow-visible">
          {NAV.map((key) => {
            const href = `${base}${PATH[key]}`;
            const active =
              key === "overview"
                ? pathname === base || pathname === `${base}/`
                : pathname.startsWith(href);
            return (
              <Link
                key={key}
                href={href}
                className={`whitespace-nowrap rounded-md px-3 py-2 text-sm transition ${
                  active
                    ? "bg-accent text-white"
                    : "text-ink/80 hover:bg-black/5 hover:text-accent"
                }`}
              >
                {m.nav[key]}
              </Link>
            );
          })}
        </nav>
        <div className="hidden border-t border-ink/10 px-5 py-4 md:block">
          <p className="truncate text-sm">{user?.full_name || user?.email}</p>
          <button
            type="button"
            onClick={() => logout()}
            className="mt-2 text-sm text-[var(--muted)] underline-offset-2 hover:text-accent hover:underline"
          >
            {m.logout}
          </button>
        </div>
      </aside>
      <main className="px-4 py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
