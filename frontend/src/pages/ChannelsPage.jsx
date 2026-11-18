import { useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CodeBlock, CopyButton, PageHeader, Panel } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { readOrgSetup } from "@/lib/setupSession";
import { getMessages } from "@/messages";

const DEMO_WIDGET_KEY = "ak_live_demo_university_key_change_me";

export default function ChannelsPage() {
  const { tenantId } = useParams();
  const [params] = useSearchParams();
  const m = getMessages();
  const [setup, setSetup] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["channels", tenantId],
    queryFn: () => tenantApi.channelConfig(tenantId),
  });

  useEffect(() => {
    setSetup(readOrgSetup(tenantId));
  }, [tenantId, params]);

  const apiBase =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

  const fullKey = useMemo(() => {
    if (setup?.widget_key) return setup.widget_key;
    // Seeded demo tenant uses a known key so Embed stays usable for testing.
    if (data?.widget_key_prefix && DEMO_WIDGET_KEY.startsWith(data.widget_key_prefix)) {
      return DEMO_WIDGET_KEY;
    }
    return null;
  }, [setup, data]);

  const snippet = useMemo(() => {
    if (setup?.embed_snippet) return setup.embed_snippet;
    if (!fullKey) return null;
    return `<script>
  window.AmakuruConfig = {
    apiBase: "${apiBase}",
    key: "${fullKey}",
    language: "en"
  };
</script>
<script src="${apiBase}/widget/amakuru-widget.js" defer></script>`;
  }, [setup, fullKey, apiBase]);

  const showSetup = params.get("setup") === "1" || !!setup?.widget_key;

  return (
    <div>
      <PageHeader
        title={m.channels.title}
        subtitle={m.channels.subtitle}
        actions={
          snippet ? (
            <CopyButton
              text={snippet}
              label={m.channels.copySnippet}
              copiedLabel={m.channels.copied}
            />
          ) : null
        }
      />

      {showSetup && snippet ? (
        <div className="mb-4 rounded-xl border border-accent/30 bg-[var(--accent-soft)] px-4 py-3 text-sm">
          {m.channels.setupBanner}
        </div>
      ) : null}

      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}

      {data && (
        <div className="grid gap-4">
          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.channels.widgetKey}
                </p>
                <p className="mt-1 break-all font-mono text-sm">{fullKey || `${data.widget_key_prefix}…`}</p>
                {!fullKey ? (
                  <p className="mt-2 text-xs text-[var(--muted)]">{m.channels.missingKey}</p>
                ) : null}
              </div>
              {fullKey ? (
                <CopyButton
                  text={fullKey}
                  label={m.channels.copyKey}
                  copiedLabel={m.channels.copied}
                />
              ) : null}
            </div>
          </Panel>

          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                  {m.channels.embed}
                </p>
                <p className="mt-2 text-sm text-[var(--muted)]">{m.channels.embedHint}</p>
              </div>
              {snippet ? (
                <CopyButton
                  text={snippet}
                  label={m.channels.copySnippet}
                  copiedLabel={m.channels.copied}
                />
              ) : null}
            </div>
            {snippet ? <CodeBlock>{snippet}</CodeBlock> : null}
          </Panel>

          <div className="grid gap-4 md:grid-cols-2">
            <Panel>
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                {m.channels.origins}
              </p>
              <p className="mt-2 text-sm">{(data.allowed_origins || []).join(", ") || "-"}</p>
            </Panel>
            <Panel>
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                {m.channels.whatsapp}
              </p>
              <p className="mt-2 text-sm">
                {data.whatsapp_enabled ? data.whatsapp_phone_number_id || "On" : "Off"}
              </p>
            </Panel>
          </div>

          <Panel>
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
              {m.channels.topics}
            </p>
            <ul className="mt-2 space-y-1 text-sm">
              {(data.quick_topics || []).map((t) => (
                <li key={t.id}>
                  <span className="font-medium">{t.label}</span>
                  <span className="text-[var(--muted)]"> · {t.prompt}</span>
                </li>
              ))}
            </ul>
          </Panel>

          <p className="text-sm text-[var(--muted)]">{m.channels.createOrgHint}</p>
        </div>
      )}
    </div>
  );
}
