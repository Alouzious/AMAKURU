"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Empty, PageHeader, Panel } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function ReviewPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { user } = useAuth();
  const qc = useQueryClient();
  const queue = useQuery({
    queryKey: ["review", tenantId],
    queryFn: () => tenantApi.reviewQueue(tenantId),
  });

  const act = useMutation({
    mutationFn: async ({
      id,
      action,
    }: {
      id: string;
      action: "approve" | "publish";
    }) => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      if (action === "approve") {
        return tenantApi.approveVersion(tenantId, id, user.csrf_token);
      }
      return tenantApi.publishVersion(tenantId, id, user.csrf_token);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["review", tenantId] });
    },
  });

  return (
    <div>
      <PageHeader title={m.review.title} />
      {queue.isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!queue.isLoading && (queue.data?.length || 0) === 0 && (
        <Empty>{m.review.empty}</Empty>
      )}
      <div className="space-y-4">
        {(queue.data || []).map((v) => (
          <Panel key={v.id}>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              v{v.version_number} · {v.status}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm">{v.answer_text}</p>
            <div className="mt-4 flex gap-2">
              <Button
                onClick={() => act.mutate({ id: v.id, action: "approve" })}
                disabled={act.isPending}
              >
                {m.answers.approve}
              </Button>
              <Button
                variant="ghost"
                onClick={() => act.mutate({ id: v.id, action: "publish" })}
                disabled={act.isPending}
              >
                {m.answers.publish}
              </Button>
            </div>
            {act.error && (
              <p className="mt-2 text-sm text-red-700">{(act.error as Error).message}</p>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}
