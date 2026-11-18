import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHeader } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function TeamPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["team", tenantId],
    queryFn: () => tenantApi.team(tenantId)
  });
  return <div>
      <PageHeader title={m.team.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!isLoading && (data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(data || []).map((member) => <li key={`${member.user_id}-${member.role}`} className="flex justify-between py-4 text-sm">
            <div>
              <p className="font-medium">{member.full_name || member.email}</p>
              <p className="text-[var(--muted)]">{member.email}</p>
            </div>
            <span className="text-[var(--muted)]">
              {m.team.role}: {member.role}
            </span>
          </li>)}
      </ul>
    </div>;
}
export {
  TeamPage as default
};
