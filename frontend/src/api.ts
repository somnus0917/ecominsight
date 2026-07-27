import type {
  AnomalyDetail,
  HealthResponse,
  JsonRecord,
  OverviewResponse,
  PaginatedResponse,
  ShopDetail,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  overview: () => request<OverviewResponse>("/api/overview"),
  shops: () => request<JsonRecord[]>("/api/shops"),
  shop: (shopId: string) =>
    request<ShopDetail>(`/api/shops/${encodeURIComponent(shopId)}`),
  products: (shopId?: string) =>
    request<JsonRecord[]>(
      `/api/products?limit=100${shopId ? `&shop_id=${encodeURIComponent(shopId)}` : ""}`,
    ),
  search: (shopId?: string) =>
    request<JsonRecord[]>(
      `/api/search?limit=100${shopId ? `&shop_id=${encodeURIComponent(shopId)}` : ""}`,
    ),
  inventory: (status?: string) =>
    request<JsonRecord[]>(
      `/api/inventory?limit=200${status ? `&status=${encodeURIComponent(status)}` : ""}`,
    ),
  finance: () => request<JsonRecord[]>("/api/finance"),
  anomalies: (params = "") =>
    request<PaginatedResponse>(`/api/anomalies?page_size=60${params}`),
  anomaly: (attributionId: string) =>
    request<AnomalyDetail>(
      `/api/anomalies/${encodeURIComponent(attributionId)}`,
    ),
  feedback: (
    attributionId: string,
    payload: {
      decision: "accepted" | "rejected" | "corrected";
      corrected_cause_code?: string;
      notes?: string;
      reviewer_alias?: string;
    },
  ) =>
    request<JsonRecord>(
      `/api/anomalies/${encodeURIComponent(attributionId)}/feedback`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
};

