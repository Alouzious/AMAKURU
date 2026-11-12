"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Empty, PageHeader, Panel } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function EvaluationPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { user } = useAuth();
  const qc = useQueryClient();
  const runs = useQuery({
    queryKey: ["eval-runs", tenantId],
    queryFn: () => tenantApi.evalRuns(tenantId),
  });
  const run = useMutation({
    mutationFn: async () => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      return tenantApi.runEval(tenantId, user.csrf_token);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["eval-runs", tenantId] });
    },
  });

  return (
    <div>
      <PageHeader
        title={m.evaluation.title}
        actions={
          <Button onClick={() => run.mutate()} disabled={run.isPending}>
            {m.evaluation.run}
          </Button>
        }
      />
      {run.data && (
        <Panel className="mb-6">
          <p className="text-sm font-medium">
            {run.data.passed ? m.evaluation.passed : m.evaluation.failed}
          </p>
          <pre className="mt-2 overflow-auto text-xs">{run.data.report}</pre>
        </Panel>
      )}
      {run.error && <p className="mb-4 text-sm text-red-700">{(run.error as Error).message}</p>}
      {runs.isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!runs.isLoading && (runs.data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(runs.data || []).map((r) => (
          <li key={r.id} className="flex justify-between gap-4 py-4 text-sm">
            <div>
              <p>
                {r.passed ? m.evaluation.passed : m.evaluation.failed} · {r.trigger}
              </p>
              <p className="mt-1 text-[var(--muted)]">
                recall@1 {(r.metrics.recall_at_1 ?? 0).toFixed(3)} · mrr{" "}
                {(r.metrics.mrr ?? 0).toFixed(3)} · top-one{" "}
                {(r.metrics.top_one_accuracy ?? 0).toFixed(3)}
              </p>
            </div>
            <span className="text-[var(--muted)]">
              {new Date(r.created_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
