import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Empty, PageHeader, Panel } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

const TYPE_LABEL = {
  sql_db: "typeSql",
  rest_json: "typeRest",
  website: "typeWebsite",
  spreadsheet: "typeSheet",
};

const DEFAULT_CONFIG = {
  sql_db: `{
  "dsn": "postgresql+psycopg://user:pass@host:5432/faq",
  "query": "SELECT question AS q, answer AS a, office AS office_name FROM faq_items"
}`,
  rest_json: `{
  "url": "https://example.edu/api/faq",
  "items_path": "items"
}`,
  website: `{
  "start_url": "https://example.edu",
  "max_pages": 15,
  "default_office": "Webmaster"
}`,
  spreadsheet: `{
  "path": "/path/to/faq.csv"
}`,
};

const DEFAULT_MAPPING = `{
  "question_raw": "q",
  "official_answer": "a",
  "owner_office": "office_name"
}`;

export default function ConnectorsPage() {
  const { tenantId } = useParams();
  const m = getMessages();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [adapterType, setAdapterType] = useState("sql_db");
  const [configText, setConfigText] = useState(DEFAULT_CONFIG.sql_db);
  const [mappingText, setMappingText] = useState(DEFAULT_MAPPING);
  const [formError, setFormError] = useState(null);
  const [syncMsg, setSyncMsg] = useState(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["connectors", tenantId],
    queryFn: () => tenantApi.connectors(tenantId),
  });

  const create = useMutation({
    mutationFn: async () => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      let config;
      let field_mapping;
      try {
        config = JSON.parse(configText || "{}");
        field_mapping = JSON.parse(mappingText || "{}");
      } catch {
        throw new Error("Config and mapping must be valid JSON");
      }
      return tenantApi.createConnector(tenantId, user.csrf_token, {
        name,
        adapter_type: adapterType,
        config,
        field_mapping,
        schedule_cron: "auto",
      });
    },
    onSuccess: async () => {
      setShowForm(false);
      setName("");
      setFormError(null);
      await qc.invalidateQueries({ queryKey: ["connectors", tenantId] });
    },
    onError: (err) => setFormError(err.message),
  });

  const sync = useMutation({
    mutationFn: async (connectorId) => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      return tenantApi.syncConnector(tenantId, connectorId, user.csrf_token);
    },
    onSuccess: async (out) => {
      setSyncMsg(
        `${m.connectors.syncOk}: ${m.connectors.drafts} ${out.drafts_created}, ${m.connectors.needs} ${out.needs_answer}`,
      );
      await qc.invalidateQueries({ queryKey: ["connectors", tenantId] });
    },
    onError: (err) => setSyncMsg(err.message),
  });

  function onTypeChange(next) {
    setAdapterType(next);
    setConfigText(DEFAULT_CONFIG[next] || "{}");
    if (next === "website") {
      setMappingText("{}");
    } else {
      setMappingText(DEFAULT_MAPPING);
    }
  }

  return (
    <div>
      <PageHeader
        title={m.connectors.title}
        subtitle={m.connectors.subtitle}
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>{m.connectors.create}</Button>
        }
      />

      {syncMsg && <p className="mb-4 text-sm text-accent">{syncMsg}</p>}
      {isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {error && <p className="text-sm text-red-700">{error.message}</p>}

      {showForm && (
        <Panel className="mb-6 space-y-3">
          <label className="block text-sm">
            {m.connectors.name}
            <input
              className="mt-1 w-full border border-ink/15 bg-white px-3 py-2"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <label className="block text-sm">
            {m.connectors.type}
            <select
              className="mt-1 w-full border border-ink/15 bg-white px-3 py-2"
              value={adapterType}
              onChange={(e) => onTypeChange(e.target.value)}
            >
              <option value="sql_db">{m.connectors.typeSql}</option>
              <option value="rest_json">{m.connectors.typeRest}</option>
              <option value="website">{m.connectors.typeWebsite}</option>
              <option value="spreadsheet">{m.connectors.typeSheet}</option>
            </select>
          </label>
          <label className="block text-sm">
            {m.connectors.config}
            <textarea
              className="mt-1 w-full border border-ink/15 bg-white px-3 py-2 font-mono text-xs"
              rows={8}
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            {m.connectors.mapping}
            <p className="mt-1 text-xs text-[var(--muted)]">{m.connectors.mappingHelp}</p>
            <textarea
              className="mt-1 w-full border border-ink/15 bg-white px-3 py-2 font-mono text-xs"
              rows={5}
              value={mappingText}
              onChange={(e) => setMappingText(e.target.value)}
            />
          </label>
          {formError && <p className="text-sm text-red-700">{formError}</p>}
          {create.error && <p className="text-sm text-red-700">{create.error.message}</p>}
          <Button
            onClick={() => create.mutate()}
            disabled={create.isPending || !name.trim()}
          >
            {m.save}
          </Button>
        </Panel>
      )}

      {!isLoading && (data?.length || 0) === 0 && !showForm && (
        <Empty>{m.connectors.empty}</Empty>
      )}

      <ul className="space-y-3">
        {(data || []).map((c) => (
          <Panel key={c.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{c.name}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {m.connectors[TYPE_LABEL[c.adapter_type]] || c.adapter_type}
                  {c.is_active ? ` · ${m.connectors.active}` : ""}
                </p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {m.connectors.lastSync}:{" "}
                  {c.last_synced_at
                    ? new Date(c.last_synced_at).toLocaleString()
                    : m.connectors.never}
                </p>
              </div>
              <Button
                onClick={() => sync.mutate(c.id)}
                disabled={sync.isPending}
                variant="ghost"
              >
                {m.connectors.sync}
              </Button>
            </div>
          </Panel>
        ))}
      </ul>
    </div>
  );
}
