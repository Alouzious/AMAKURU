import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";

export default function HomePage() {
  const { user, loading, login, logout } = useAuth();
  const navigate = useNavigate();
  const m = getMessages();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (loading || !user) return;
    // Same flow as before: sign in → open first organization dashboard.
    if (user.memberships?.[0]) {
      navigate(`/t/${user.memberships[0].tenant_id}`, { replace: true });
    }
  }, [loading, user, navigate]);

  async function onSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
    } catch {
      setError(m.loginFailed);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
        {m.loading}
      </main>
    );
  }

  if (user) {
    return (
      <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-8 px-6 py-12">
        <header>
          <p className="font-display text-3xl text-accent">{m.brand}</p>
          <h1 className="mt-2 text-lg font-medium">{m.memberships}</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {m.welcome}, {user.full_name || user.email}
          </p>
        </header>

        {user.is_platform_admin ? (
          <Link to="/onboard" className="ui-btn-primary w-full text-center">
            {m.nav.newOrg}
          </Link>
        ) : null}

        <section className="ui-panel overflow-hidden">
          <div className="border-b border-[var(--line)] px-4 py-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
              {m.nav.yourOrgs}
            </h2>
          </div>
          <ul>
            {(user.memberships || []).length === 0 ? (
              <li className="px-4 py-6 text-sm text-[var(--muted)]">{m.empty}</li>
            ) : (
              user.memberships.map((mem) => (
                <li
                  key={`${mem.tenant_id}-${mem.role}`}
                  className="border-b border-[var(--line)] last:border-0"
                >
                  <Link
                    to={`/t/${mem.tenant_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-3 transition hover:bg-[var(--accent-soft)]"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{mem.tenant_name}</p>
                      <p className="text-xs text-[var(--muted)]">
                        {mem.role}
                        {mem.is_demo ? ` · ${m.demoBadge}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 text-sm font-medium text-accent">
                      {m.openDashboard}
                    </span>
                  </Link>
                </li>
              ))
            )}
          </ul>
        </section>

        <button
          type="button"
          onClick={() => logout()}
          className="text-sm text-[var(--muted)] hover:text-accent"
        >
          {m.logout}
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-8 px-6 py-12">
      <header>
        <p className="font-display text-4xl text-accent">{m.brand}</p>
        <p className="mt-2 text-sm text-[var(--muted)]">{m.tagline}</p>
      </header>
      <form onSubmit={onSubmit} className="ui-panel space-y-4 p-5">
        <div>
          <h1 className="text-lg font-semibold">{m.loginTitle}</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">{m.loginSubtitle}</p>
        </div>
        <label className="ui-label">
          {m.email}
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="ui-input mt-1.5"
          />
        </label>
        <label className="ui-label">
          {m.password}
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="ui-input mt-1.5"
          />
        </label>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
        <button type="submit" disabled={submitting} className="ui-btn-primary w-full">
          {submitting ? m.signingIn : m.submit}
        </button>
      </form>
    </main>
  );
}
