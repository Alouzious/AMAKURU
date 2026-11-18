import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Empty, PageHeader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function SearchesPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { user } = useAuth();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["searches", tenantId],
    queryFn: () => tenantApi.searchEvents(tenantId),
  });

  const promote = useMutation({
    mutationFn: async () => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      return tenantApi.promoteSearches(tenantId, user.csrf_token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["searches", tenantId] }),
  });

  return (
    <div>
      <PageHeader
        title={m.searches.title}
        subtitle={m.searches.subtitle}
        actions={
          <Button onClick={() => promote.mutate()} disabled={promote.isPending}>
            {m.searches.promote}
          </Button>
        }
      />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {error && <p className="text-sm text-red-700">{error.message}</p>}
      {promote.data?.message && (
        <p className="mb-4 text-sm text-accent">{promote.data.message}</p>
      )}
      {promote.error && (
        <p className="mb-4 text-sm text-red-700">{promote.error.message}</p>
      )}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.searches.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(data || []).map((item) => (
          <li key={item.id} className="flex flex-wrap items-start justify-between gap-4 py-4 text-sm">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{item.question}</p>
              <p className="mt-1 text-[var(--muted)]">
                {item.language} · {item.channel} · {m.searches.decision}: {item.decision}
                {item.promoted ? ` · ${m.searches.promoted}` : ""}
              </p>
            </div>
            <div className="text-right text-[var(--muted)]">
              <p>
                {m.searches.count}: {item.count}
              </p>
              <p className="mt-1">
                {item.answered ? m.searches.answered : m.searches.unanswered}
              </p>
              <p className="mt-1 text-xs">
                {item.last_asked_at ? new Date(item.last_asked_at).toLocaleString() : ""}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
