import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { listPlans, onboardTenant } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";
function OnboardPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const m = getMessages();
  const [plans, setPlans] = useState([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [plan, setPlan] = useState("starter");
  const [language, setLanguage] = useState("en");
  const [accent, setAccent] = useState("#0F4C5C");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminName, setAdminName] = useState("Tenant Administrator");
  const [adminPassword, setAdminPassword] = useState("ChangeMeNow123!");
  const [seedAnswers, setSeedAnswers] = useState(true);
  const [isDemo, setIsDemo] = useState(true);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    if (!loading && !user) navigate("/", { replace: true });
  }, [loading, user, navigate]);
  useEffect(() => {
    void listPlans().then((p) => setPlans(p.map((x) => ({ code: x.code, name: x.name })))).catch(() => setPlans([
      { code: "starter", name: "Starter" },
      { code: "campus", name: "Campus" },
      { code: "enterprise", name: "Enterprise" }
    ]));
  }, []);
  if (loading || !user) {
    return <main className="mx-auto flex min-h-screen max-w-lg items-center justify-center px-6">
        <p className="text-sm text-[var(--muted)]">{m.loading}</p>
      </main>;
  }
  if (!user.is_platform_admin) {
    return <main className="mx-auto max-w-lg px-6 py-16">
        <p className="text-sm">{m.forbidden || "Platform admin required."}</p>
        <Link to="/" className="mt-4 inline-block text-accent underline">
          Home
        </Link>
      </main>;
  }
  async function onSubmit(event) {
    event.preventDefault();
    if (!user?.csrf_token) return;
    setSubmitting(true);
    setError(null);
    try {
      const out = await onboardTenant(user.csrf_token, {
        name,
        slug,
        plan,
        default_language: language,
        accent,
        admin_email: adminEmail,
        admin_full_name: adminName,
        admin_password: adminPassword,
        seed_demo_answers: seedAnswers,
        is_demo: isDemo,
        offices: []
      });
      setResult(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onboarding failed");
    } finally {
      setSubmitting(false);
    }
  }
  return <main className="mx-auto max-w-2xl px-6 py-16">
      <header className="mb-8 space-y-2">
        <p className="font-display text-4xl tracking-tight text-accent">{m.brand}</p>
        <h1 className="text-2xl font-medium">{m.onboard.title}</h1>
        <p className="text-sm text-[var(--muted)]">{m.onboard.subtitle}</p>
      </header>

      {result ? <section className="space-y-4 text-sm">
          <p className="font-medium">{m.onboard.success}</p>
          <p>{result.message}</p>
          <div>
            <p className="text-xs uppercase text-[var(--muted)]">{m.onboard.widgetKey}</p>
            <p className="mt-1 break-all font-mono text-xs">{result.widget_key}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-[var(--muted)]">{m.onboard.embed}</p>
            <pre className="mt-1 overflow-x-auto rounded bg-black/5 p-3 text-xs">
              {result.embed_snippet}
            </pre>
          </div>
          <Link to={`/t/${result.tenant_id}`} className="inline-block text-accent underline">
            Open dashboard
          </Link>
        </section> : <form className="space-y-4" onSubmit={onSubmit}>
          <label className="block text-sm">
            {m.onboard.name}
            <input
    required
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={name}
    onChange={(e) => setName(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.slug}
            <input
    required
    pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={slug}
    onChange={(e) => setSlug(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.plan}
            <select
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={plan}
    onChange={(e) => setPlan(e.target.value)}
  >
              {plans.map((p) => <option key={p.code} value={p.code}>
                  {p.name}
                </option>)}
            </select>
          </label>
          <label className="block text-sm">
            {m.onboard.language}
            <input
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={language}
    onChange={(e) => setLanguage(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.accent}
            <input
    type="color"
    className="mt-1 block h-10 w-24"
    value={accent}
    onChange={(e) => setAccent(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.adminEmail}
            <input
    required
    type="email"
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={adminEmail}
    onChange={(e) => setAdminEmail(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.adminName}
            <input
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={adminName}
    onChange={(e) => setAdminName(e.target.value)}
  />
          </label>
          <label className="block text-sm">
            {m.onboard.adminPassword}
            <input
    required
    type="password"
    minLength={12}
    className="mt-1 w-full border border-ink/15 bg-transparent px-3 py-2"
    value={adminPassword}
    onChange={(e) => setAdminPassword(e.target.value)}
  />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
    type="checkbox"
    checked={seedAnswers}
    onChange={(e) => setSeedAnswers(e.target.checked)}
  />
            {m.onboard.seedAnswers}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isDemo} onChange={(e) => setIsDemo(e.target.checked)} />
            {m.onboard.isDemo}
          </label>
          {error && <p className="text-sm text-red-800">{error}</p>}
          <button
    type="submit"
    disabled={submitting}
    className="bg-accent px-5 py-2 text-sm text-white disabled:opacity-50"
  >
            {m.onboard.submit}
          </button>
        </form>}
    </main>;
}
export {
  OnboardPage as default
};
