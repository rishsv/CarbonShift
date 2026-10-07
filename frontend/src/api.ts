// Central API client for CarbonShift AI
export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Health ───────────────────────────────────────────────────────────────────
export const fetchHealth = () => apiFetch<any>('/health');

// ── Metrics ──────────────────────────────────────────────────────────────────
export const fetchMetrics = () => apiFetch<any>('/metrics/impact');

// ── Jobs ─────────────────────────────────────────────────────────────────────
export const fetchJobs = (params?: { status?: string; priority?: number }) => {
  const qs = params ? '?' + new URLSearchParams(params as any).toString() : '';
  return apiFetch<any[]>(`/jobs${qs}`);
};

export const createJob = (body: any) =>
  apiFetch<any>('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const deleteJob = (id: string) =>
  fetch(`${API_BASE}/jobs/${id}`, { method: 'DELETE' });

export const parseNLJob = (text: string) =>
  apiFetch<any>('/jobs/nl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });

export const estimateJob = (body: any) =>
  apiFetch<any>('/jobs/estimate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

// ── Sites ────────────────────────────────────────────────────────────────────
export const fetchSites = () => apiFetch<any[]>('/sites');

// ── Forecast ─────────────────────────────────────────────────────────────────
export const fetchForecast = (region: string, hours = 48) =>
  apiFetch<any>(`/forecast?region=${region}&hours=${hours}`);

export const fetchGreenWindows = (region?: string, hours = 12) => {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (region) qs.set('region', region);
  return apiFetch<any[]>(`/forecast/windows?${qs}`);
};

export const fetchForecastAccuracy = () => apiFetch<any>('/forecast/accuracy');

// ── Grid ─────────────────────────────────────────────────────────────────────
export const fetchGridNow = () => apiFetch<any>('/grid/now');

export const fetchGridHistory = (region: string, from: string, to: string) =>
  apiFetch<any>(`/grid/history?region=${region}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);

// ── Schedule ──────────────────────────────────────────────────────────────────
export const triggerSchedule = (opts?: {
  strategy?: string;
  horizon_hours?: number;
  risk_lambda?: number;
  allow_spatial?: boolean;
  carbon_budget_kg?: number | null;
  preset?: string;
  solver_seconds?: number;
}) =>
  apiFetch<any>('/schedule', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy: 'cpsat',
      horizon_hours: 48,
      risk_lambda: 0.3,
      allow_spatial: true,
      preset: 'balanced',
      solver_seconds: 15,
      ...opts,
    }),
  });

export const fetchRuns = (limit = 10) => apiFetch<any[]>(`/schedule/runs?limit=${limit}`);

export const fetchRun = (runId: string) => apiFetch<any>(`/schedule/runs/${runId}`);

export const compareStrategies = (horizon_hours = 48) =>
  apiFetch<any>(`/schedule/compare?horizon_hours=${horizon_hours}`);

// ── Simulate ──────────────────────────────────────────────────────────────────
export const runWhatIf = (params: any) =>
  apiFetch<any>('/simulate/whatif', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });

// ── Config ────────────────────────────────────────────────────────────────────
export const fetchConfig = () => apiFetch<any>('/config');

// ── Demo ─────────────────────────────────────────────────────────────────────
export const resetDemo = () =>
  apiFetch<any>('/demo/reset', { method: 'POST' });

// ── Legacy compat exports ─────────────────────────────────────────────────────
export const fetchGridForecast = fetchForecast;
export const runCompare = compareStrategies;
