"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PageHeader, Panel } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function ChannelsPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["channels", tenantId],
    queryFn: () => tenantApi.channelConfig(tenantId),
  });
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";
  const snippet = `<script>
  window.AmakuruConfig = {
    apiBase: "${apiBase}",
    key: "YOUR_WIDGET_KEY",
    language: "en"
  };
</script>
<script src="${apiBase}/widget/amakuru-widget.js" defer></script>`;

  return (
    <div>
      <PageHeader title={m.channels.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              {m.channels.widgetKey}
            </p>
            <p className="mt-1 font-mono text-sm">{data.widget_key_prefix}…</p>
            <p className="mt-4 text-xs uppercase tracking-wide text-[var(--muted)]">
              {m.channels.origins}
            </p>
            <p className="mt-1 text-sm">{(data.allowed_origins || []).join(", ") || "—"}</p>
            <p className="mt-4 text-xs uppercase tracking-wide text-[var(--muted)]">
              {m.channels.whatsapp}
            </p>
            <p className="mt-1 text-sm">
              {data.whatsapp_enabled
                ? data.whatsapp_phone_number_id || "enabled"
                : "disabled"}
            </p>
          </Panel>
          <Panel>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              {m.channels.topics}
            </p>
            <ul className="mt-2 space-y-1 text-sm">
              {(data.quick_topics || []).map((t) => (
                <li key={t.id}>
                  {t.label} — <span className="text-[var(--muted)]">{t.prompt}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel className="lg:col-span-2">
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              {m.channels.embed}
            </p>
            <pre className="mt-2 overflow-auto bg-black/5 p-3 text-xs">{snippet}</pre>
            <p className="mt-2 text-sm text-[var(--muted)]">{data.welcome_message}</p>
          </Panel>
        </div>
      )}
    </div>
  );
}
