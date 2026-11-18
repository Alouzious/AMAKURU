import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui";
import { downloadUsageCsv, tenantApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getMessages } from "@/messages";
function BillingPage() {
  const params = useParams();
  const tenantId = params.tenantId;
  const m = getMessages();
  const { user } = useAuth();
  const csrf = user?.csrf_token;
  const qc = useQueryClient();
  const [keyName, setKeyName] = useState("Integration key");
  const [createdKey, setCreatedKey] = useState(null);
  const [error, setError] = useState(null);
  const billing = useQuery({
    queryKey: ["billing", tenantId],
    queryFn: () => tenantApi.billing(tenantId)
  });
  const usage = useQuery({
    queryKey: ["usage", tenantId],
    queryFn: () => tenantApi.usage(tenantId)
  });
  const keys = useQuery({
    queryKey: ["api-keys", tenantId],
    queryFn: () => tenantApi.apiKeys(tenantId)
  });
  const createKey = useMutation({
    mutationFn: () => {
      if (!csrf) throw new Error("Missing CSRF");
      return tenantApi.createApiKey(tenantId, csrf, keyName);
    },
    onSuccess: (data) => {
      setCreatedKey(data.raw_key);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["api-keys", tenantId] });
    },
    onError: (err) => setError(err.message)
  });
  const revokeKey = useMutation({
    mutationFn: (id) => {
      if (!csrf) throw new Error("Missing CSRF");
      return tenantApi.revokeApiKey(tenantId, id, csrf);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["api-keys", tenantId] })
  });
  const b = billing.data;
  const u = b?.usage;
  return <div className="space-y-8">
      <PageHeader title={m.billing.title} />

      <Panel>
        {billing.isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
        {b && <div className="space-y-4">
            <div>
              <p className="text-sm text-[var(--muted)]">{m.billing.plan}</p>
              <p className="font-display text-2xl text-accent">{b.plan_detail.name}</p>
              <p className="mt-1 text-sm text-[var(--muted)]">{b.plan_detail.description}</p>
              <p className="mt-2 text-xs text-[var(--muted)]">
                {m.billing.residency}: {b.residency_mode}
              </p>
            </div>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">
                  {m.billing.published}
                </dt>
                <dd className="text-lg">
                  {u?.published_answers ?? 0} / {u?.published_answers_limit ?? 0}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">
                  {m.billing.conversations}
                </dt>
                <dd className="text-lg">
                  {u?.answered_conversations_month ?? 0} /{" "}
                  {u?.answered_conversations_limit ?? 0}
                </dd>
              </div>
            </dl>
            <button
    type="button"
    className="inline-block text-sm text-accent underline"
    onClick={async () => {
      const blob = await downloadUsageCsv(tenantId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `amakuru-usage-${tenantId}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }}
  >
              {m.billing.export}
            </button>
          </div>}
      </Panel>

      <Panel>
        <h2 className="font-display text-xl">{m.billing.usageTitle}</h2>
        <ul className="mt-3 space-y-1 text-sm">
          {(usage.data || []).slice(0, 20).map((row) => <li key={`${row.day}-${row.event_type}`} className="flex justify-between gap-4">
              <span>
                {row.day} · {row.event_type}
              </span>
              <span>
                {row.quantity} · ${Number(row.estimated_cost_usd).toFixed(6)}
              </span>
            </li>)}
          {!usage.data?.length && <li className="text-[var(--muted)]">{m.billing.noUsage}</li>}
        </ul>
      </Panel>

      <Panel>
        <h2 className="font-display text-xl">{m.billing.apiKeys}</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">{m.billing.apiKeysHelp}</p>
        {error && <p className="mt-2 text-sm text-red-800">{error}</p>}
        {createdKey && <p className="mt-2 break-all rounded bg-black/5 p-3 font-mono text-xs">
            {createdKey}
          </p>}
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            {m.billing.keyName}
            <input
    className="mt-1 block w-56 border border-ink/15 bg-transparent px-3 py-2"
    value={keyName}
    onChange={(e) => setKeyName(e.target.value)}
  />
          </label>
          <button
    type="button"
    className="bg-accent px-4 py-2 text-sm text-white disabled:opacity-50"
    disabled={createKey.isPending || !csrf}
    onClick={() => createKey.mutate()}
  >
            {m.billing.createKey}
          </button>
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {(keys.data || []).map((k) => <li key={k.id} className="flex items-center justify-between gap-3 border-b border-ink/10 py-2">
              <div>
                <p className="font-medium">{k.name}</p>
                <p className="text-xs text-[var(--muted)]">
                  {k.key_prefix}… · {k.scopes.join(", ")}
                  {k.revoked_at ? ` \xB7 ${m.billing.revoked}` : ""}
                </p>
              </div>
              {!k.revoked_at && <button
    type="button"
    className="text-sm text-red-800"
    onClick={() => revokeKey.mutate(k.id)}
  >
                  {m.billing.revoke}
                </button>}
            </li>)}
        </ul>
      </Panel>
    </div>;
}
export {
  BillingPage as default
};
