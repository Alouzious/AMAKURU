const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function api(path, init = {}, csrf) {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    let detailMsg = null;
    if (typeof detail === "string") {
      detailMsg = detail;
    } else if (Array.isArray(detail)) {
      detailMsg = detail
        .map((d) => {
          const loc = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
          return loc ? `${loc}: ${d.msg}` : d.msg;
        })
        .join("; ");
    }
    throw new Error(detailMsg || body?.message || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined;
  return res.json();
}

export async function login(email, password) {
  const data = await api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return data.user;
}

export async function fetchMe() {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Failed to load session");
  return res.json();
}

export async function logout(csrfToken) {
  await api("/api/v1/auth/logout", { method: "POST" }, csrfToken);
}

export const tenantApi = {
  overview: (tenantId) => api(`/api/v1/tenants/${tenantId}/overview`),
  entries: (tenantId) => api(`/api/v1/tenants/${tenantId}/answer-entries`),
  entry: (tenantId, entryId) =>
    api(`/api/v1/tenants/${tenantId}/answer-entries/${entryId}`),
  versions: (tenantId, entryId) =>
    api(`/api/v1/tenants/${tenantId}/answer-entries/${entryId}/versions`),
  reviewQueue: (tenantId) => api(`/api/v1/tenants/${tenantId}/review-queue`),
  expiring: (tenantId) => api(`/api/v1/tenants/${tenantId}/expiring-soon`),
  unanswered: (tenantId) => api(`/api/v1/tenants/${tenantId}/unanswered`),
  conversations: (tenantId) => api(`/api/v1/tenants/${tenantId}/conversations`),
  conversation: (tenantId, id) =>
    api(`/api/v1/tenants/${tenantId}/conversations/${id}`),
  trace: (tenantId, id) => api(`/api/v1/tenants/${tenantId}/traces/${id}`),
  evalRuns: (tenantId) => api(`/api/v1/tenants/${tenantId}/eval-runs`),
  runEval: (tenantId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/eval-runs`, { method: "POST" }, csrf),
  channelConfig: (tenantId) => api(`/api/v1/tenants/${tenantId}/channel-config`),
  team: (tenantId) => api(`/api/v1/tenants/${tenantId}/team`),
  audit: (tenantId) => api(`/api/v1/tenants/${tenantId}/audit-log`),
  offices: (tenantId) => api(`/api/v1/tenants/${tenantId}/offices`),
  createEntry: (tenantId, csrf, body) =>
    api(
      `/api/v1/tenants/${tenantId}/answer-entries`,
      { method: "POST", body: JSON.stringify(body) },
      csrf,
    ),
  submitVersion: (tenantId, versionId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/versions/${versionId}/submit`, { method: "POST" }, csrf),
  approveVersion: (tenantId, versionId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/versions/${versionId}/approve`, { method: "POST" }, csrf),
  publishVersion: (tenantId, versionId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/versions/${versionId}/publish`, { method: "POST" }, csrf),
  tenant: (tenantId) => api(`/api/v1/tenants/${tenantId}`),
  billing: (tenantId) => api(`/api/v1/tenants/${tenantId}/billing`),
  usage: (tenantId) => api(`/api/v1/tenants/${tenantId}/usage`),
  apiKeys: (tenantId) => api(`/api/v1/tenants/${tenantId}/api-keys`),
  createApiKey: (tenantId, csrf, name) =>
    api(
      `/api/v1/tenants/${tenantId}/api-keys`,
      { method: "POST", body: JSON.stringify({ name, scopes: ["ask"] }) },
      csrf,
    ),
  revokeApiKey: (tenantId, keyId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/api-keys/${keyId}`, { method: "DELETE" }, csrf),
  connectors: (tenantId) => api(`/api/v1/tenants/${tenantId}/connectors`),
  createConnector: (tenantId, csrf, body) =>
    api(
      `/api/v1/tenants/${tenantId}/connectors`,
      { method: "POST", body: JSON.stringify(body) },
      csrf,
    ),
  syncConnector: (tenantId, connectorId, csrf) =>
    api(
      `/api/v1/tenants/${tenantId}/connectors/${connectorId}/sync`,
      { method: "POST" },
      csrf,
    ),
  searchEvents: (tenantId) => api(`/api/v1/tenants/${tenantId}/search-events`),
  promoteSearches: (tenantId, csrf) =>
    api(`/api/v1/tenants/${tenantId}/search-events/promote`, { method: "POST" }, csrf),
};

export async function listPlans() {
  return api("/api/v1/plans");
}

export async function onboardTenant(csrf, body) {
  return api("/api/v1/onboarding", { method: "POST", body: JSON.stringify(body) }, csrf);
}

export async function downloadUsageCsv(tenantId) {
  const res = await fetch(`${API_BASE}/api/v1/tenants/${tenantId}/usage/export`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Usage export failed");
  return res.blob();
}
