import { useParams, useNavigate, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/Shell";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";
function TenantLayout() {
  const { tenantId } = useParams();
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const m = getMessages();
  useEffect(() => {
    if (!loading && !user) navigate("/", { replace: true });
  }, [loading, user, navigate]);
  const tenant = useQuery({
    queryKey: ["tenant", tenantId],
    queryFn: () => tenantApi.tenant(tenantId),
    enabled: !!user && !!tenantId
  });
  if (loading || !user) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
        {m.loading}
      </main>;
  }
  return <Shell
    tenantId={tenantId}
    tenantName={tenant.data?.name || "\u2026"}
    accent={tenant.data?.branding?.accent}
  >
      <Outlet />
    </Shell>;
}
export {
  TenantLayout as default
};
