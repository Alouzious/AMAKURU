const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type Membership = {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  is_demo: boolean;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  memberships: Membership[];
  csrf_token?: string | null;
};

async function api<T>(
  path: string,
  init: RequestInit = {},
  csrf?: string | null,
): Promise<T> {
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
    const body = (await res.json().catch(() => null)) as { message?: string } | null;
    throw new Error(body?.message || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function login(email: string, password: string): Promise<User> {
  const data = await api<{ user: User }>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return data.user;
}

export async function fetchMe(): Promise<User | null> {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Failed to load session");
  return (await res.json()) as User;
}

export async function logout(csrfToken: string): Promise<void> {
  await api("/api/v1/auth/logout", { method: "POST" }, csrfToken);
}

export type Overview = {
  answered_share: number;
  unanswered_open: number;
  expiring_soon: number;
  published_entries: number;
  conversations_7d: number;
  feedback_up: number;
  feedback_down: number;
  language_mix: Record<string, number>;
  channel_mix: Record<string, number>;
  top_questions: { question: string; count: number }[];
};

export type Entry = {
  id: string;
  office_id: string;
  category: string;
  subcategory: string;
  verbatim_only: boolean;
  escalate_to_human: boolean;
  latest_status?: string | null;
};

export type Version = {
  id: string;
  entry_id: string;
  version_number: number;
  answer_text: string;
  status: string;
  valid_until: string | null;
  last_verified: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  channel: string;
  language: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_preview: string | null;
};

export type Trace = {
  id: string;
  question: string;
  language: string;
  decision: string;
  steps: unknown[];
  candidates: unknown[];
  latency_ms: number;
  tokens: number;
  estimated_cost_usd: number;
  cache_hit: boolean;
  created_at: string;
};

export const tenantApi = {
  overview: (tenantId: string) => api<Overview>(`/api/v1/tenants/${tenantId}/overview`),
  entries: (tenantId: string) =>
    api<Entry[]>(`/api/v1/tenants/${tenantId}/answer-entries`),
  entry: (tenantId: string, entryId: string) =>
    api<Entry & { versions?: Version[] }>(
      `/api/v1/tenants/${tenantId}/answer-entries/${entryId}`,
    ),
  versions: (tenantId: string, entryId: string) =>
    api<Version[]>(`/api/v1/tenants/${tenantId}/answer-entries/${entryId}/versions`),
  reviewQueue: (tenantId: string) =>
    api<Version[]>(`/api/v1/tenants/${tenantId}/review-queue`),
  expiring: (tenantId: string) =>
    api<Version[]>(`/api/v1/tenants/${tenantId}/expiring-soon`),
  unanswered: (tenantId: string) =>
    api<
      {
        id: string;
        question: string;
        language: string;
        channel: string;
        count: number;
        status: string;
      }[]
    >(`/api/v1/tenants/${tenantId}/unanswered`),
  conversations: (tenantId: string) =>
    api<Conversation[]>(`/api/v1/tenants/${tenantId}/conversations`),
  conversation: (tenantId: string, id: string) =>
    api<{
      conversation: Conversation;
      messages: {
        id: string;
        role: string;
        content: string;
        trace_id: string | null;
        meta: Record<string, unknown>;
        created_at: string;
      }[];
    }>(`/api/v1/tenants/${tenantId}/conversations/${id}`),
  trace: (tenantId: string, id: string) =>
    api<Trace>(`/api/v1/tenants/${tenantId}/traces/${id}`),
  evalRuns: (tenantId: string) =>
    api<
      {
        id: string;
        trigger: string;
        metrics: Record<string, number>;
        passed: boolean;
        created_at: string;
      }[]
    >(`/api/v1/tenants/${tenantId}/eval-runs`),
  runEval: (tenantId: string, csrf: string) =>
    api<{ passed: boolean; metrics: Record<string, number>; report: string }>(
      `/api/v1/tenants/${tenantId}/eval-runs`,
      { method: "POST" },
      csrf,
    ),
  channelConfig: (tenantId: string) =>
    api<{
      widget_key_prefix: string;
      allowed_origins: string[];
      whatsapp_enabled: boolean;
      whatsapp_phone_number_id: string | null;
      quick_topics: { id: string; label: string; prompt: string }[];
      welcome_message: string;
    }>(`/api/v1/tenants/${tenantId}/channel-config`),
  team: (tenantId: string) =>
    api<
      { user_id: string; email: string; full_name: string; role: string; office_id: string | null }[]
    >(`/api/v1/tenants/${tenantId}/team`),
  audit: (tenantId: string) =>
    api<
      {
        id: string;
        action: string;
        resource_type: string;
        resource_id: string | null;
        created_at: string;
      }[]
    >(`/api/v1/tenants/${tenantId}/audit-log`),
  offices: (tenantId: string) =>
    api<{ id: string; name: string; email: string; phone: string }[]>(
      `/api/v1/tenants/${tenantId}/offices`,
    ),
  createEntry: (
    tenantId: string,
    csrf: string,
    body: Record<string, unknown>,
  ) =>
    api<Entry>(
      `/api/v1/tenants/${tenantId}/answer-entries`,
      { method: "POST", body: JSON.stringify(body) },
      csrf,
    ),
  submitVersion: (tenantId: string, versionId: string, csrf: string) =>
    api<Version>(
      `/api/v1/tenants/${tenantId}/versions/${versionId}/submit`,
      { method: "POST" },
      csrf,
    ),
  approveVersion: (tenantId: string, versionId: string, csrf: string) =>
    api<Version>(
      `/api/v1/tenants/${tenantId}/versions/${versionId}/approve`,
      { method: "POST" },
      csrf,
    ),
  publishVersion: (tenantId: string, versionId: string, csrf: string) =>
    api<Version>(
      `/api/v1/tenants/${tenantId}/versions/${versionId}/publish`,
      { method: "POST" },
      csrf,
    ),
  tenant: (tenantId: string) =>
    api<{
      id: string;
      name: string;
      slug: string;
      plan: string;
      status: string;
      residency_mode: string;
      branding: {
        accent?: string;
        display_name?: string;
        logo_url?: string;
        surface?: string;
        heading_font?: string;
        custom_domain?: string;
      };
      default_language: string;
      is_demo: boolean;
    }>(`/api/v1/tenants/${tenantId}`),
  billing: (tenantId: string) =>
    api<{
      plan: string;
      plan_detail: {
        code: string;
        name: string;
        description: string;
        entitlements: Record<string, unknown>;
      };
      entitlements: Record<string, unknown>;
      usage: {
        published_answers: number;
        published_answers_limit: number;
        answered_conversations_month: number;
        answered_conversations_limit: number;
      };
      residency_mode: string;
      branding: Record<string, unknown>;
    }>(`/api/v1/tenants/${tenantId}/billing`),
  usage: (tenantId: string) =>
    api<
      {
        day: string;
        event_type: string;
        quantity: number;
        estimated_cost_usd: number;
      }[]
    >(`/api/v1/tenants/${tenantId}/usage`),
  apiKeys: (tenantId: string) =>
    api<
      {
        id: string;
        name: string;
        key_prefix: string;
        scopes: string[];
        created_at: string;
        last_used_at: string | null;
        revoked_at: string | null;
      }[]
    >(`/api/v1/tenants/${tenantId}/api-keys`),
  createApiKey: (tenantId: string, csrf: string, name: string) =>
    api<{
      id: string;
      name: string;
      key_prefix: string;
      scopes: string[];
      created_at: string;
      last_used_at: string | null;
      revoked_at: string | null;
      raw_key: string;
    }>(
      `/api/v1/tenants/${tenantId}/api-keys`,
      { method: "POST", body: JSON.stringify({ name, scopes: ["ask"] }) },
      csrf,
    ),
  revokeApiKey: (tenantId: string, keyId: string, csrf: string) =>
    api(
      `/api/v1/tenants/${tenantId}/api-keys/${keyId}`,
      { method: "DELETE" },
      csrf,
    ),
};

export async function listPlans(): Promise<
  { code: string; name: string; description: string; entitlements: Record<string, unknown> }[]
> {
  return api("/api/v1/plans");
}

export async function onboardTenant(
  csrf: string,
  body: Record<string, unknown>,
): Promise<{
  tenant_id: string;
  slug: string;
  plan: string;
  widget_key: string;
  embed_snippet: string;
  admin_email: string;
  offices_created: number;
  message: string;
}> {
  return api("/api/v1/onboarding", { method: "POST", body: JSON.stringify(body) }, csrf);
}

export async function downloadUsageCsv(tenantId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/tenants/${tenantId}/usage/export`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Usage export failed");
  return res.blob();
}
