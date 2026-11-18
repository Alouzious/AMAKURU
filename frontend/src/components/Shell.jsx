import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMemo, useState } from "react";
import OnboardModal from "@/components/OnboardModal";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";

const PRIMARY = [
  { key: "overview", path: "" },
  { key: "answers", path: "/answers" },
  { key: "channels", path: "/channels" },
];

const ORG_TOOLS = [
  { key: "connectors", path: "/connectors" },
  { key: "searches", path: "/searches" },
  { key: "conversations", path: "/conversations" },
  { key: "review", path: "/review" },
  { key: "gaps", path: "/gaps" },
  { key: "expiring", path: "/expiring" },
  { key: "evaluation", path: "/evaluation" },
  { key: "team", path: "/team" },
  { key: "settings", path: "/settings" },
  { key: "billing", path: "/billing" },
  { key: "audit", path: "/audit" },
];

function navActive(pathname, base, path, isOverview) {
  const href = `${base}${path}`;
  if (isOverview) return pathname === base || pathname === `${base}/`;
  return pathname.startsWith(href);
}

export function Shell({ tenantId, tenantName, accent, children }) {
  const pathname = useLocation().pathname;
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const m = getMessages();
  const base = `/t/${tenantId}`;

  const orgToolActive = useMemo(
    () => ORG_TOOLS.some((item) => navActive(pathname, base, item.path, false)),
    [pathname, base],
  );
  const [orgOpen, setOrgOpen] = useState(orgToolActive);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const orgs = user?.memberships || [];

  function goOrg(id) {
    setSwitcherOpen(false);
    navigate(`/t/${id}`);
  }

  return (
    <div
      className="min-h-screen md:grid md:grid-cols-[240px_1fr]"
      style={accent ? { ["--accent"]: accent } : undefined}
    >
      <aside className="flex flex-col border-b border-[var(--line)] bg-white md:min-h-screen md:border-b-0 md:border-r">
        <div className="px-3 pt-4">
          <Link to="/" className="px-1 font-display text-lg text-accent">
            {m.brand}
          </Link>

          <div className="relative mt-3">
            <button
              type="button"
              onClick={() => setSwitcherOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[var(--paper)] px-3 py-2.5 text-left transition hover:border-accent/40"
            >
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.nav.currentOrg}
                </p>
                <p className="truncate text-sm font-semibold">{tenantName}</p>
              </div>
              <span className="text-xs text-[var(--muted)]">{switcherOpen ? "▴" : "▾"}</span>
            </button>

            {switcherOpen ? (
              <div className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded-xl border border-[var(--line)] bg-white shadow-lg">
                <p className="border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.nav.yourOrgs}
                </p>
                <ul className="max-h-64 overflow-auto">
                  {orgs.length === 0 ? (
                    <li className="px-3 py-3 text-sm text-[var(--muted)]">{m.empty}</li>
                  ) : (
                    orgs.map((mem) => {
                      const active = mem.tenant_id === tenantId;
                      return (
                        <li key={`${mem.tenant_id}-${mem.role}`}>
                          <button
                            type="button"
                            onClick={() => goOrg(mem.tenant_id)}
                            className={`flex w-full items-start justify-between gap-2 px-3 py-2.5 text-left text-sm ${
                              active ? "bg-[var(--accent-soft)] text-accent" : "hover:bg-[var(--paper)]"
                            }`}
                          >
                            <span className="min-w-0">
                              <span className="block truncate font-medium">{mem.tenant_name}</span>
                              <span className="block text-xs text-[var(--muted)]">
                                {mem.tenant_slug || mem.role}
                                {mem.is_demo ? ` · ${m.demoBadge}` : ""}
                              </span>
                            </span>
                            {active ? <span className="text-xs">●</span> : null}
                          </button>
                        </li>
                      );
                    })
                  )}
                </ul>
                <div className="border-t border-[var(--line)] p-2">
                  {user?.is_platform_admin ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSwitcherOpen(false);
                        setCreateOpen(true);
                      }}
                      className="block w-full rounded-lg px-2 py-2 text-left text-sm font-medium text-accent hover:bg-[var(--accent-soft)]"
                    >
                      {m.nav.newOrg}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <nav className="mt-4 flex-1 space-y-1 px-2 pb-4">
          {PRIMARY.map((item) => {
            const href = `${base}${item.path}`;
            const active = navActive(pathname, base, item.path, item.key === "overview");
            return (
              <Link
                key={item.key}
                to={href}
                className={`block rounded-lg px-2.5 py-2 text-sm transition ${
                  active
                    ? "bg-accent text-white"
                    : "text-[var(--ink)]/85 hover:bg-[var(--accent-soft)] hover:text-accent"
                }`}
              >
                {m.nav[item.key]}
              </Link>
            );
          })}

          <div className="pt-3">
            <button
              type="button"
              onClick={() => setOrgOpen((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm text-[var(--muted)] hover:bg-[var(--paper)] hover:text-accent"
            >
              <span className="font-medium">{m.nav.orgTools}</span>
              <span className="text-xs">{orgOpen || orgToolActive ? "▴" : "▾"}</span>
            </button>
            {(orgOpen || orgToolActive) && (
              <div className="mt-1 space-y-0.5 border-l border-[var(--line)] ml-2 pl-2">
                {ORG_TOOLS.map((item) => {
                  const href = `${base}${item.path}`;
                  const active = navActive(pathname, base, item.path, false);
                  return (
                    <Link
                      key={item.key}
                      to={href}
                      className={`block rounded-lg px-2 py-1.5 text-sm transition ${
                        active
                          ? "bg-[var(--accent-soft)] font-medium text-accent"
                          : "text-[var(--ink)]/75 hover:text-accent"
                      }`}
                    >
                      {m.nav[item.key]}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </nav>

        <div className="border-t border-[var(--line)] px-4 py-4">
          <p className="truncate text-xs text-[var(--muted)]">{user?.email}</p>
          <button
            type="button"
            onClick={() => logout()}
            className="mt-2 text-xs text-[var(--muted)] hover:text-accent"
          >
            {m.logout}
          </button>
        </div>
      </aside>
      <main className="px-4 py-5 md:px-8 md:py-7" onClick={() => setSwitcherOpen(false)}>
        {children}
      </main>
      {user?.is_platform_admin ? (
        <OnboardModal open={createOpen} onClose={() => setCreateOpen(false)} />
      ) : null}
    </div>
  );
}
