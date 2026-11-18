import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function AuditPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["audit", tenantId],
    queryFn: () => tenantApi.audit(tenantId)
  });
  return <div>
      <PageHeader title={m.audit.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(data || []).map((row) => <li key={row.id} className="flex justify-between gap-4 py-3 text-sm">
            <div>
              <p className="font-medium">{row.action}</p>
              <p className="text-[var(--muted)]">
                {row.resource_type}
                {row.resource_id ? ` \xB7 ${row.resource_id}` : ""}
              </p>
            </div>
            <span className="text-[var(--muted)]">
              {new Date(row.created_at).toLocaleString()}
            </span>
          </li>)}
      </ul>
    </div>;
}
export {
  AuditPage as default
};
