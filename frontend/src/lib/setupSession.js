const KEY = "amakuru.setup";

export function saveOrgSetup(payload) {
  sessionStorage.setItem(KEY, JSON.stringify(payload));
}

export function readOrgSetup(tenantId) {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (tenantId && data.tenant_id !== tenantId) return null;
    return data;
  } catch {
    return null;
  }
}

export function clearOrgSetup() {
  sessionStorage.removeItem(KEY);
}
