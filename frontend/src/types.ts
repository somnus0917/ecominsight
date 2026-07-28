export type JsonRecord = Record<string, unknown>;

export interface HealthResponse {
  status: "ok" | "degraded";
  database_exists: boolean;
  feedback_store_ready: boolean;
  data_updated_at: string | null;
  data_mode: "real" | "demo";
}

export interface KpiValue {
  code: string;
  label: string;
  value: number;
  unit: string;
}

export interface TrendPoint {
  date: string;
  paid_amount: number;
  paid_orders: number;
  refund_amount: number;
  ad_spend: number;
  settlement_amount: number;
}

export interface OverviewResponse {
  data_updated_at: string | null;
  kpis: KpiValue[];
  trend: TrendPoint[];
  shops: JsonRecord[];
}

export interface PaginatedResponse {
  items: JsonRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface ShopDetail {
  shop_id: string;
  trend: JsonRecord[];
  carriers: JsonRecord[];
  channels: JsonRecord[];
}

export interface AnomalyDetail {
  event: JsonRecord;
  candidates: JsonRecord[];
  evidence: JsonRecord[];
  trend: JsonRecord[];
  report: {
    summary?: string;
    confirmed_facts?: Array<{ fact: string; evidence_ids: string[] }>;
    possible_causes?: Array<{
      cause: string;
      confidence: number;
      status: string;
      evidence_ids: string[];
    }>;
    missing_information?: string[];
    recommended_checks?: string[];
  } | null;
  validation: JsonRecord | null;
  feedback: JsonRecord[];
}

