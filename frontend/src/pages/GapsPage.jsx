import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function GapsPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["gaps", tenantId],
    queryFn: () => tenantApi.unanswered(tenantId)
  });
  return <div>
      <PageHeader title={m.gaps.title} subtitle={m.gaps.subtitle} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(data || []).map((item) => <li key={item.id} className="flex justify-between gap-4 py-4 text-sm">
            <div>
              <p>{item.question}</p>
              <p className="mt-1 text-[var(--muted)]">
                {item.language} · {item.channel}
              </p>
            </div>
            <span className="text-[var(--muted)]">
              {m.gaps.count}: {item.count}
            </span>
          </li>)}
      </ul>
    </div>;
}
export {
  GapsPage as default
};
