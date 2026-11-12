"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PageHeader, Panel } from "@/components/ui";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function SettingsPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { data, isLoading } = useQuery({
    queryKey: ["tenant", tenantId],
    queryFn: () => tenantApi.tenant(tenantId),
  });

  return (
    <div>
      <PageHeader title={m.settings.title} />
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {data && (
        <Panel className="max-w-xl space-y-3 text-sm">
          <p>
            <strong>{m.settings.name}:</strong> {data.name}
          </p>
          <p>
            <strong>{m.settings.slug}:</strong> {data.slug}
          </p>
          <p>
            <strong>{m.settings.language}:</strong> {data.default_language}
          </p>
          <p>
            <strong>{m.settings.accent}:</strong>{" "}
            <span style={{ color: data.branding?.accent || "var(--accent)" }}>
              {data.branding?.accent || "#0f4c5c"}
            </span>
          </p>
          {data.is_demo && <p className="text-[var(--muted)]">{m.settings.demoTenant}</p>}
        </Panel>
      )}
    </div>
  );
}
