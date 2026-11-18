import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader, Panel } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function ExpiringPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["expiring", tenantId],
    queryFn: () => tenantApi.expiring(tenantId)
  });
  return <div>
      <PageHeader title={m.expiring.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.expiring.empty}</Empty>}
      <div className="space-y-3">
        {(data || []).map((v) => <Panel key={v.id}>
            <p className="text-xs text-[var(--muted)]">Valid until {v.valid_until || "\u2014"}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm">{v.answer_text}</p>
          </Panel>)}
      </div>
    </div>;
}
export {
  ExpiringPage as default
};
