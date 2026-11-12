"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader, Panel, Stat } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function OverviewPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview", tenantId],
    queryFn: () => tenantApi.overview(tenantId),
  });

  return (
    <div>
      <PageHeader title={m.overview.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {error && <p className="text-sm text-red-700">{(error as Error).message}</p>}
      {data && (
        <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
          <div className="grid gap-2 sm:grid-cols-2">
            <Stat
              label={m.overview.answeredShare}
              value={`${Math.round(data.answered_share * 100)}%`}
            />
            <Stat label={m.overview.unanswered} value={String(data.unanswered_open)} />
            <Stat label={m.overview.expiring} value={String(data.expiring_soon)} />
            <Stat label={m.overview.published} value={String(data.published_entries)} />
            <Stat label={m.overview.conversations} value={String(data.conversations_7d)} />
            <Stat
              label={m.overview.satisfaction}
              value={`${data.feedback_up}↑ / ${data.feedback_down}↓`}
            />
          </div>
          <div className="space-y-4">
            <Panel>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
                {m.overview.topQuestions}
              </h2>
              {data.top_questions.length === 0 ? (
                <Empty>{m.empty}</Empty>
              ) : (
                <ul className="space-y-3">
                  {data.top_questions.map((q) => (
                    <li key={q.question} className="flex justify-between gap-4 border-b border-ink/5 pb-2 text-sm">
                      <span>{q.question}</span>
                      <span className="text-[var(--muted)]">{q.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
                {m.overview.languageMix}
              </h2>
              <p className="text-sm">
                {Object.entries(data.language_mix)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || m.empty}
              </p>
              <h2 className="mb-2 mt-5 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
                {m.overview.channelMix}
              </h2>
              <p className="text-sm">
                {Object.entries(data.channel_mix)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || m.empty}
              </p>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
