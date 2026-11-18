import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";
function HomePage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const m = getMessages();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    if (!loading && user?.memberships?.[0]) {
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
    return <main className="mx-auto flex min-h-screen max-w-lg items-center justify-center px-6">
        <p className="text-sm text-[var(--muted)]">{m.loading}</p>
      </main>;
  }
  if (user) {
    return <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 px-6 py-16">
        <header className="space-y-2">
          <p className="font-display text-4xl tracking-tight text-accent">{m.brand}</p>
          <h1 className="text-2xl font-medium">
            {m.welcome}, {user.full_name || user.email}
          </h1>
        </header>
        {user.is_platform_admin && <p>
            <Link to="/onboard" className="text-sm text-accent underline">
              Set up organization
            </Link>
          </p>}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            {m.memberships}
          </h2>
          <ul className="space-y-2">
            {user.memberships.map((mem) => <li key={`${mem.tenant_id}-${mem.role}`}>
                <Link
      href={`/t/${mem.tenant_id}`}
      className="flex items-center justify-between border-b border-black/10 py-3 transition hover:text-accent"
    >
                  <div>
                    <p className="font-medium">{mem.tenant_name}</p>
                    <p className="text-sm text-[var(--muted)]">
                      {mem.role}
                      {mem.is_demo ? ` \xB7 ${m.demoBadge}` : ""}
                    </p>
                  </div>
                  <span className="text-sm">{m.openDashboard}</span>
                </Link>
              </li>)}
          </ul>
        </section>
      </main>;
  }
  return <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-10 px-6 py-16">
      <header className="space-y-3">
        <p className="font-display text-5xl tracking-tight text-accent">{m.brand}</p>
        <p className="text-[var(--muted)]">{m.tagline}</p>
      </header>
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="space-y-2">
          <h1 className="text-xl font-medium">{m.loginTitle}</h1>
          <p className="text-sm text-[var(--muted)]">{m.loginSubtitle}</p>
        </div>
        <label className="block space-y-1.5 text-sm">
          <span>{m.email}</span>
          <input
    type="email"
    required
    autoComplete="username"
    value={email}
    onChange={(e) => setEmail(e.target.value)}
    className="w-full border border-ink/15 bg-white/70 px-3 py-2 outline-none ring-accent focus:ring-2"
  />
        </label>
        <label className="block space-y-1.5 text-sm">
          <span>{m.password}</span>
          <input
    type="password"
    required
    autoComplete="current-password"
    value={password}
    onChange={(e) => setPassword(e.target.value)}
    className="w-full border border-ink/15 bg-white/70 px-3 py-2 outline-none ring-accent focus:ring-2"
  />
        </label>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button
    type="submit"
    disabled={submitting}
    className="w-full bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
  >
          {submitting ? m.signingIn : m.submit}
        </button>
      </form>
    </main>;
}
export {
  HomePage as default
};
