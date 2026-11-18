import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function ConversationsPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["conversations", tenantId],
    queryFn: () => tenantApi.conversations(tenantId)
  });
  return <div>
      <PageHeader title={m.conversations.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(data || []).map((c) => <li key={c.id}>
            <Link
    href={`/t/${tenantId}/conversations/${c.id}`}
    className="flex justify-between gap-4 py-4 text-sm transition hover:text-accent"
  >
              <div>
                <p>{c.last_preview || c.id.slice(0, 8)}</p>
                <p className="mt-1 text-[var(--muted)]">
                  {c.channel} · {c.language} · {c.message_count} msgs
                </p>
              </div>
              <span className="text-[var(--muted)]">
                {new Date(c.updated_at).toLocaleString()}
              </span>
            </Link>
          </li>)}
      </ul>
    </div>;
}
export {
  ConversationsPage as default
};
