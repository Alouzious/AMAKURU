"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/Shell";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function TenantLayout({ children }: { children: React.ReactNode }) {
  const { tenantId } = useParams<{ tenantId: string }>();
  const { user, loading } = useAuth();
  const router = useRouter();
  const m = getMessages();

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  const tenant = useQuery({
    queryKey: ["tenant", tenantId],
    queryFn: () => tenantApi.tenant(tenantId),
    enabled: !!user && !!tenantId,
  });

  if (loading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
        {m.loading}
      </main>
    );
  }

  return (
    <Shell
      tenantId={tenantId}
      tenantName={tenant.data?.name || "…"}
      accent={tenant.data?.branding?.accent}
    >
      {children}
    </Shell>
  );
}
