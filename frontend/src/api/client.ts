import axios from "axios";

export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE ?? "/api" });

// 后端只返回 {code, params}，不返回自然语言；前端按当前语言渲染
export class ApiError extends Error {
  constructor(public code: string, public params: Record<string, unknown> = {}, public status = 0) {
    super(code);
  }
}
http.interceptors.response.use(
  (r) => r,
  (e) => {
    const d = e?.response?.data?.detail;
    if (d && typeof d === "object" && d.code) throw new ApiError(d.code, d.params ?? {}, e.response.status);
    throw new ApiError("UNKNOWN", {}, e?.response?.status ?? 0);
  },
);

export interface DatasetInfo { key: string; label: string; coord_system: string; instances: number; active: boolean }
export interface InstanceSummary {
  name: string; dataset: string; tasks: number; clients: number; tcs: number; tractors: number; trailers: number;
  coord_system: string; meta: { day?: string; day_label?: string; week?: string; day_note?: string; group?: string; fictional?: boolean; scenario?: boolean; label?: string; base?: string };
}
export interface Cost { fuel: number; driver: number; tractor_fixed: number; trailer_fixed: number; outsource: number; penalty: number; total: number;
  drivers: { km: number; driver_hours: number; tractors_owned: number; tractors_used: number; trailers_total: number; penalty_minutes: number; unfinished: number } }
export interface RecordedRun { run_id: string; instance: string; dataset: string; method: string; mode: string | null; runtime_s: number | null; recorded: true }
export interface RunRecord {
  run_id: string; status: string; method: string; dataset: string; instance: string; mode?: string | null; inventory_mode: string; tractors: number;
  runtime_s: number; totals: { unfinished: number; mileage_km: number; early_penalty: number; late_penalty: number; total_penalty: number };
  l2: Record<string, number>; cost: Cost; currency: string; price_version: string; trace?: [number, number][] | null;
  verified: { feasible: boolean; violations: { code: string; detail: string }[]; on_time_rate: number | null; tractors_used: number };
  recorded?: boolean;
  progress?: { elapsed_s: number; best_cost: number; iterations: number }; error?: { code: string; detail?: string };
}
export interface CompareColumn { method: string; cost: number; cost_std?: number; km: number; on_time_rate: number; unfinished: number; runtime_s: number;
  penalty_min?: number; vs_manual_pct: number; vs_traditional_pct?: number; wait_hours?: number; budget_s?: number; seeds?: number; trace?: [number, number][] }
export interface CompareResp { dataset: string; instance: string; tractors: number; currency: string; columns: CompareColumn[]; advanced?: CompareColumn[]; price_version: string;
  min_tractors?: { C0: number | null; H0: number | null; "M0-R": number | null } | null;
  serve_all?: { method: string; tractors: number; cost: number; unfinished: number; km: number; vs_traditional_pct: number }[] | null }
export interface WeekDay { day: string; label: string; tasks: number; tractors: number; note: string; min_tractors?: { C0: number | null; H0: number | null } | null; cost: Record<string, number>; km: Record<string, number>; on_time_rate: Record<string, number> }
export interface WeekResp { currency: string; price_version: string; days: WeekDay[]; week_total: Record<string, { cost: number; vs_manual_pct: number; vs_traditional_pct?: number | null }>;
  serve_all_total?: Record<string, { cost: number; vs_traditional_pct: number }> | null }
export interface PriceTable { fuel_l_per_100km: number; fuel_price_per_l: number; driver_per_hour: number; tractor_fixed_per_day: number;
  trailer_fixed_per_day: number; outsource_per_task: number; penalty_per_minute: number; currency: string; version: string; current: string; versions: string[]; sources: Record<string, string> }
export interface ScalingRow { n: number; seed: number; m4_proven_optimal: boolean; m4_runtime_s: number; m4_gap: number; M3: { gap_vs_m4_best: number } }

export const get = async <T,>(url: string, params?: Record<string, unknown>) => (await http.get<T>(url, { params })).data;
