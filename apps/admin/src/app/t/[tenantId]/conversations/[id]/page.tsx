"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PageHeader, Panel } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function ConversationDetailPage() {
  const { tenantId, id } = useParams<{ tenantId: string; id: string }>();
  const m = getMessages();
  const detail = useQuery({
    queryKey: ["conversation", tenantId, id],
    queryFn: () => tenantApi.conversation(tenantId, id),
  });
  const traceId = detail.data?.messages.find((x) => x.trace_id)?.trace_id;
  const trace = useQuery({
    queryKey: ["trace", tenantId, traceId],
    queryFn: () => tenantApi.trace(tenantId, traceId!),
    enabled: !!traceId,
  });

  return (
    <div>
      <PageHeader title={m.conversations.title} subtitle={id.slice(0, 8)} />
      {detail.isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            {m.conversations.messages}
          </h2>
          <div className="space-y-3">
            {(detail.data?.messages || []).map((msg) => (
              <div key={msg.id} className="border-b border-ink/5 pb-3 text-sm">
                <p className="text-xs uppercase text-[var(--muted)]">{msg.role}</p>
                <p className="mt-1 whitespace-pre-wrap">{msg.content}</p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            {m.conversations.why}
          </h2>
          {!trace.data && <p className="text-sm text-[var(--muted)]">{m.empty}</p>}
          {trace.data && (
            <div className="space-y-2 text-sm">
              <p>
                <strong>{m.conversations.decision}:</strong> {trace.data.decision}
              </p>
              <p>
                <strong>{m.conversations.latency}:</strong> {trace.data.latency_ms} ms
              </p>
              <p>
                <strong>{m.conversations.cost}:</strong> $
                {trace.data.estimated_cost_usd.toFixed(6)}
              </p>
              <p>
                <strong>{m.conversations.cache}:</strong>{" "}
                {trace.data.cache_hit ? "hit" : "miss"}
              </p>
              <pre className="mt-3 max-h-80 overflow-auto bg-black/5 p-3 text-xs">
                {JSON.stringify(trace.data.steps, null, 2)}
              </pre>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
