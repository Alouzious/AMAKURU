import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listPlans, onboardTenant } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";
import { saveOrgSetup } from "@/lib/setupSession";
import { Button, CodeBlock, CopyButton } from "@/components/ui";

const SOURCE_OPTIONS = [
  { id: "demo", labelKey: "sourceDemo" },
  { id: "paste", labelKey: "sourcePaste" },
  { id: "sql_db", labelKey: "sourceSql" },
  { id: "rest_json", labelKey: "sourceApi" },
  { id: "website", labelKey: "sourceWebsite" },
  { id: "none", labelKey: "sourceNone" },
];

export default function OnboardModal({ open, onClose }) {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const m = getMessages();
  const [plans, setPlans] = useState([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [plan, setPlan] = useState("starter");
  const [language, setLanguage] = useState("en");
  const [accent, setAccent] = useState("#0b6e4f");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminName, setAdminName] = useState("Tenant Administrator");
  const [adminPassword, setAdminPassword] = useState("ChangeMeNow123!");
  const [isDemo, setIsDemo] = useState(false);
  const [knowledgeSource, setKnowledgeSource] = useState("demo");
  const [siteOrigin, setSiteOrigin] = useState("");
  const [pasteText, setPasteText] = useState(
    "What are the tuition fees?\tUGX 1,200,000 per semester (sample).\nHow do I apply?\tCreate an account on the admissions portal.",
  );
  const [sqlDsn, setSqlDsn] = useState("");
  const [sqlQuery, setSqlQuery] = useState(
    "SELECT question AS q, answer AS a, office AS office_name FROM faq_items",
  );
  const [restUrl, setRestUrl] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setError(null);
    void listPlans()
      .then((p) => setPlans(p.map((x) => ({ code: x.code, name: x.name }))))
      .catch(() =>
        setPlans([
          { code: "starter", name: "Starter" },
          { code: "campus", name: "Campus" },
          { code: "enterprise", name: "Enterprise" },
        ]),
      );
  }, [open]);

  useEffect(() => {
    if (!name || result) return;
    const next = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 64);
    setSlug((prev) => (prev ? prev : next));
  }, [name, result]);

  if (!open) return null;

  function parsePastePairs(text) {
    const pairs = [];
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      let question;
      let answer;
      if (trimmed.includes("\t")) [question, answer] = trimmed.split("\t");
      else if (trimmed.includes("|")) [question, answer] = trimmed.split("|");
      else if (trimmed.includes("::")) [question, answer] = trimmed.split("::");
      else continue;
      question = (question || "").trim();
      answer = (answer || "").trim();
      if (question && answer) pairs.push({ question, answer });
    }
    return pairs;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (!user?.csrf_token) return;
    setSubmitting(true);
    setError(null);
    try {
      const cleanSlug = slug
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      if (!cleanSlug || cleanSlug.length < 2 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(cleanSlug)) {
        throw new Error(m.onboard.slugError);
      }
      if (!adminEmail.trim() || !adminEmail.includes("@")) {
        throw new Error(m.onboard.emailError);
      }
      if (adminPassword.length < 12) {
        throw new Error(m.onboard.passwordError);
      }
      setSlug(cleanSlug);
      const body = {
        name: name.trim(),
        slug: cleanSlug,
        plan,
        default_language: (language || "en").trim(),
        accent,
        admin_email: adminEmail.trim(),
        admin_full_name: adminName.trim() || "Tenant Administrator",
        admin_password: adminPassword,
        seed_demo_answers: knowledgeSource === "demo",
        is_demo: isDemo || knowledgeSource === "demo",
        offices: [],
        knowledge_source: knowledgeSource,
        allowed_origins: siteOrigin.trim() ? [siteOrigin.trim()] : ["*"],
      };
      if (siteOrigin.trim()) body.site_origin = siteOrigin.trim();
      if (knowledgeSource === "paste") {
        body.paste_pairs = parsePastePairs(pasteText);
        if (!body.paste_pairs.length) throw new Error(m.onboard.pasteError);
      }
      if (knowledgeSource === "sql_db") {
        if (!sqlDsn.trim() || !sqlQuery.trim()) throw new Error(m.onboard.sqlRequired);
        body.sql_dsn = sqlDsn.trim();
        body.sql_query = sqlQuery.trim();
      }
      if (knowledgeSource === "rest_json") {
        if (!restUrl.trim()) throw new Error(m.onboard.restRequired);
        body.rest_url = restUrl.trim();
      }
      if (knowledgeSource === "website") {
        if (!websiteUrl.trim()) throw new Error(m.onboard.websiteRequired);
        body.website_start_url = websiteUrl.trim();
      }
      const out = await onboardTenant(user.csrf_token, body);
      saveOrgSetup({
        tenant_id: out.tenant_id,
        widget_key: out.widget_key,
        embed_snippet: out.embed_snippet,
        slug: out.slug,
      });
      await refresh().catch(() => null);
      setResult(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onboarding failed");
    } finally {
      setSubmitting(false);
    }
  }

  function stayHere() {
    onClose?.();
  }

  function openNewOrg() {
    if (!result?.tenant_id) return;
    onClose?.();
    navigate(`/t/${result.tenant_id}/channels?setup=1`);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 md:p-8">
      <div
        className="absolute inset-0"
        onClick={result ? undefined : onClose}
        aria-hidden
      />
      <div className="relative z-10 my-4 w-full max-w-xl rounded-2xl border border-[var(--line)] bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
          <div>
            <h2 className="font-display text-xl">{m.onboard.title}</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {result ? m.onboard.successStay : m.onboard.subtitle}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-[var(--muted)] hover:bg-[var(--paper)] hover:text-accent"
          >
            {m.onboard.close}
          </button>
        </div>

        <div className="max-h-[75vh] overflow-y-auto px-5 py-4">
          {result ? (
            <div className="space-y-4">
              <p className="text-sm font-medium text-accent">{m.onboard.success}</p>
              <p className="text-sm text-[var(--muted)]">{m.onboard.embedHint}</p>
              <div className="flex flex-wrap gap-2">
                <CopyButton
                  text={result.embed_snippet}
                  label={m.onboard.copySnippet}
                  copiedLabel={m.onboard.copied}
                />
                <CopyButton
                  text={result.widget_key}
                  label={m.onboard.copyKey}
                  copiedLabel={m.onboard.copied}
                />
              </div>
              <CodeBlock>{result.embed_snippet}</CodeBlock>
              <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={stayHere}>{m.onboard.doneStay}</Button>
                <Button variant="ghost" onClick={openNewOrg}>
                  {m.onboard.openChannels}
                </Button>
              </div>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={onSubmit}>
              <section className="space-y-3">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.onboard.sectionOrg}
                </h3>
                <label className="ui-label">
                  {m.onboard.name}
                  <input
                    required
                    className="ui-input mt-1.5"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label className="ui-label">
                  {m.onboard.slug}
                  <input
                    required
                    minLength={2}
                    pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                    className="ui-input mt-1.5 font-mono text-xs"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  />
                  <span className="ui-help">{m.onboard.slugHint}</span>
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="ui-label">
                    {m.onboard.plan}
                    <select
                      className="ui-input mt-1.5"
                      value={plan}
                      onChange={(e) => setPlan(e.target.value)}
                    >
                      {plans.map((p) => (
                        <option key={p.code} value={p.code}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="ui-label">
                    {m.onboard.language}
                    <input
                      className="ui-input mt-1.5"
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                    />
                  </label>
                </div>
                <label className="ui-label">
                  {m.onboard.siteOrigin}
                  <input
                    placeholder="https://www.their-site.com"
                    className="ui-input mt-1.5"
                    value={siteOrigin}
                    onChange={(e) => setSiteOrigin(e.target.value)}
                  />
                </label>
              </section>

              <section className="space-y-3 border-t border-[var(--line)] pt-4">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.onboard.sectionAdmin}
                </h3>
                <label className="ui-label">
                  {m.onboard.adminEmail}
                  <input
                    required
                    type="email"
                    className="ui-input mt-1.5"
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                  />
                </label>
                <label className="ui-label">
                  {m.onboard.adminName}
                  <input
                    className="ui-input mt-1.5"
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                  />
                </label>
                <label className="ui-label">
                  {m.onboard.adminPassword}
                  <input
                    required
                    type="password"
                    minLength={12}
                    className="ui-input mt-1.5"
                    value={adminPassword}
                    onChange={(e) => setAdminPassword(e.target.value)}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={isDemo}
                    onChange={(e) => setIsDemo(e.target.checked)}
                  />
                  {m.onboard.isDemo}
                </label>
              </section>

              <section className="space-y-3 border-t border-[var(--line)] pt-4">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.onboard.sectionKnowledge}
                </h3>
                <fieldset className="space-y-2">
                  {SOURCE_OPTIONS.map((opt) => (
                    <label key={opt.id} className="flex items-start gap-2 text-sm">
                      <input
                        type="radio"
                        name="knowledge_source_modal"
                        className="mt-1"
                        checked={knowledgeSource === opt.id}
                        onChange={() => setKnowledgeSource(opt.id)}
                      />
                      <span>{m.onboard[opt.labelKey]}</span>
                    </label>
                  ))}
                </fieldset>
                {knowledgeSource === "paste" && (
                  <textarea
                    rows={5}
                    className="ui-input font-mono text-xs"
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                  />
                )}
                {knowledgeSource === "sql_db" && (
                  <div className="space-y-2">
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder={m.onboard.sqlDsn}
                      className="ui-input font-mono text-xs"
                      value={sqlDsn}
                      onChange={(e) => setSqlDsn(e.target.value)}
                    />
                    <textarea
                      rows={3}
                      className="ui-input font-mono text-xs"
                      value={sqlQuery}
                      onChange={(e) => setSqlQuery(e.target.value)}
                    />
                  </div>
                )}
                {knowledgeSource === "rest_json" && (
                  <input
                    className="ui-input"
                    placeholder={m.onboard.restUrl}
                    value={restUrl}
                    onChange={(e) => setRestUrl(e.target.value)}
                  />
                )}
                {knowledgeSource === "website" && (
                  <input
                    className="ui-input"
                    placeholder={m.onboard.websiteUrl}
                    value={websiteUrl}
                    onChange={(e) => setWebsiteUrl(e.target.value)}
                  />
                )}
              </section>

              {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
              <div className="flex gap-2">
                <button type="button" className="ui-btn-ghost flex-1" onClick={onClose}>
                  {m.onboard.close}
                </button>
                <button type="submit" disabled={submitting} className="ui-btn-primary flex-1">
                  {submitting ? m.onboard.submitting : m.onboard.submit}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
