/**
 * Client API front LGC — communication avec le backend FastAPI local.
 */

// Base vide = appels relatifs (même origine que le front) : le rewrite Next
// (next.config.ts) proxifie /api vers le backend. Marche sur Mac et téléphone
// sans CORS. Un override absolu via NEXT_PUBLIC_API_URL reste possible.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * Extrait un message lisible d'une réponse d'erreur FastAPI.
 * `detail` peut être une string (HTTPException) OU une liste d'objets
 * {loc, msg} (erreurs de validation Pydantic) — ce dernier cas produisait
 * « [object Object] ». On concatène alors « champ : message ».
 */
function extractErrorMessage(err: unknown, statusCode: number): string {
  const fallback = `HTTP ${statusCode}`;
  if (!err || typeof err !== 'object') return fallback;
  const detail = (err as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (!d || typeof d !== 'object') return String(d);
        const loc = Array.isArray((d as { loc?: unknown[] }).loc)
          ? (d as { loc: unknown[] }).loc.slice(1).join('.')
          : '';
        const msg = (d as { msg?: string }).msg ?? '';
        return loc ? `${loc} : ${msg}` : msg;
      })
      .filter(Boolean);
    if (msgs.length) return msgs.join(' · ');
  }
  return fallback;
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, response.status));
  }
  if (response.status === 204) return {} as T;
  return response.json();
}

const get = <T>(e: string) => fetchAPI<T>(e);
const post = <T>(e: string, body?: unknown) =>
  fetchAPI<T>(e, { method: 'POST', body: JSON.stringify(body ?? {}) });
const put = <T>(e: string, body?: unknown) =>
  fetchAPI<T>(e, { method: 'PUT', body: JSON.stringify(body ?? {}) });
const patch = <T>(e: string, body?: unknown) =>
  fetchAPI<T>(e, { method: 'PATCH', body: JSON.stringify(body ?? {}) });
const del = (e: string) => fetchAPI<void>(e, { method: 'DELETE' });

export const healthAPI = {
  check: () => get<{ status: string }>('/health'),
};

export const settingsAPI = {
  get: () => get<Record<string, unknown>>('/api/settings'),
  update: (body: Record<string, unknown>) =>
    put<Record<string, unknown>>('/api/settings', body),
};

export type OpeningControl = {
  implied: string;
  movements: string;
  diff: string;
  status: 'ok' | 'warn';
};
export type OpeningRow = {
  account_uid: string;
  name: string;
  provider: string;
  currency: string;
  balance: string | null;
  current_balance: string;
  rate: string;
  control: OpeningControl | null;
};
export type OpeningsView = {
  year: number;
  accounts: OpeningRow[];
  tie_out: { opening_eur: string; current_eur: string; reconciles: boolean };
};

export const openingsAPI = {
  years: () => get<{ years: number[] }>('/api/opening-balances/years'),
  get: (year: number) => get<OpeningsView>(`/api/opening-balances?year=${year}`),
  save: (year: number, items: { account_uid: string; balance: string }[]) =>
    put<OpeningsView>(`/api/opening-balances?year=${year}`, { items }),
};

export const clientsAPI = {
  list: () => get<any[]>('/api/clients'),
  create: (b: Record<string, unknown>) => post<any>('/api/clients', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/clients/${id}`, b),
  remove: (id: number) => del(`/api/clients/${id}`),
  repricePreview: (id: number) =>
    get<RepricePreview>(`/api/clients/${id}/forecast-reprice-preview`),
  reprice: (id: number) =>
    post<RepricePreview>(`/api/clients/${id}/forecast-reprice`),
};

export type RepriceRow = {
  month: string;
  quantity: string;
  unit: string;
  old_amount: string;
  new_amount: string;
  old_amount_eur: string;
  new_amount_eur: string;
};

export type RepricePreview = {
  from_month: string;
  count: number;
  currency: string;
  rate: string;
  rate_unit: string;
  rows: RepriceRow[];
  total_old: string;
  total_new: string;
  total_old_eur: string;
  total_new_eur: string;
};

export const transactionsAPI = {
  list: (params?: Record<string, string | number | boolean | undefined>) => {
    const q = params
      ? '?' +
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== '')
          .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
          .join('&')
      : '';
    return get<any[]>(`/api/transactions${q}`);
  },
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/transactions/${id}`, b),
  bulkCategorize: (ids: number[], category_id: number | null) =>
    post<any[]>('/api/transactions/bulk-categorize', { ids, category_id }),
};

export const categoriesAPI = {
  list: () => get<any[]>('/api/categories'),
  create: (b: Record<string, unknown>) => post<any>('/api/categories', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/categories/${id}`, b),
  remove: (id: number) => del(`/api/categories/${id}`),
  recategorize: () => post<{ changed: number }>('/api/categories/recategorize'),
  listRules: () => get<any[]>('/api/category-rules'),
  createRule: (b: Record<string, unknown>) => post<any>('/api/category-rules', b),
  updateRule: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/category-rules/${id}`, b),
  deleteRule: (id: number) => del(`/api/category-rules/${id}`),
};

export const treasuryAPI = {
  get: (asOf?: string) =>
    get<any>(`/api/treasury${asOf ? `?as_of=${asOf}` : ''}`),
  pnl: (year = new Date().getFullYear()) => get<any>(`/api/pnl?year=${year}`),
};

export const fxAPI = {
  list: () => get<any[]>('/api/fx-rates'),
  save: (rates: { currency: string; rate: string | number }[]) =>
    put<any[]>('/api/fx-rates', { rates }),
};

export const balanceDocsAPI = {
  list: (accountUid?: string) =>
    get<any[]>(`/api/balance-docs${accountUid ? `?account_uid=${accountUid}` : ''}`),
  upload: async (
    file: File,
    meta?: { account_uid?: string; label?: string; doc_date?: string },
  ) => {
    const fd = new FormData();
    fd.append('file', file);
    if (meta?.account_uid) fd.append('account_uid', meta.account_uid);
    if (meta?.label) fd.append('label', meta.label);
    if (meta?.doc_date) fd.append('doc_date', meta.doc_date);
    const res = await fetch(`${API_BASE_URL}/api/balance-docs`, {
      method: 'POST',
      body: fd, // pas de Content-Type manuel → boundary multipart auto
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(e.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  downloadUrl: (id: number) => `${API_BASE_URL}/api/balance-docs/${id}/download`,
  remove: (id: number) => del(`/api/balance-docs/${id}`),
};

export const investmentsAPI = {
  list: () => get<any[]>('/api/manual-assets'),
  create: (b: Record<string, unknown>) => post<any>('/api/manual-assets', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/manual-assets/${id}`, b),
  remove: (id: number) => del(`/api/manual-assets/${id}`),
  summary: () => get<any>('/api/manual-assets/summary'),
};

export const forecastAPI = {
  get: (year = new Date().getFullYear(), startingCash?: number, includeIssued = false) =>
    get<any>(
      `/api/forecast?year=${year}` +
        (startingCash !== undefined ? `&starting_cash_eur=${startingCash}` : '') +
        (includeIssued ? '&include_issued=true' : ''),
    ),
  save: (b: Record<string, unknown>) => put<any>('/api/forecast', b),
  deleteInput: (clientId: number, month: string) =>
    del(`/api/forecast/${clientId}/${month}`),
};

export const invoicesAPI = {
  list: () => get<any[]>('/api/invoices'),
  get: (id: number) => get<any>(`/api/invoices/${id}`),
  create: (b: Record<string, unknown>) => post<any>('/api/invoices', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/invoices/${id}`, b),
  generate: (id: number) => post<any>(`/api/invoices/${id}/generate`),
  rollback: (id: number) => post<any>(`/api/invoices/${id}/rollback`),
  candidates: (id: number) => get<any[]>(`/api/invoices/${id}/candidates`),
  reconcile: (id: number, transaction_id: number) =>
    post<any>(`/api/invoices/${id}/reconcile`, { transaction_id }),
  unreconcile: (id: number) => post<any>(`/api/invoices/${id}/unreconcile`),
  remove: (id: number) => del(`/api/invoices/${id}`),
  printUrl: (id: number) => `${API_BASE_URL}/api/invoices/${id}/print`,
  generatePdf: (id: number) => post<{ pdf_path: string }>(`/api/invoices/${id}/pdf`),
  downloadUrl: (id: number) => `${API_BASE_URL}/api/invoices/${id}/download`,
};

export type Scope = 'realized' | 'engaged' | 'forecast';

export const dashboardAPI = {
  cashflow: (year = new Date().getFullYear(), scope: Scope = 'forecast') =>
    get<any>(`/api/dashboard/cashflow?year=${year}&scope=${scope}`),
  balanceTimeline: (year = new Date().getFullYear(), scope: Scope = 'forecast') =>
    get<any>(`/api/dashboard/balance-timeline?year=${year}&scope=${scope}`),
  pnlSummary: (year = new Date().getFullYear(), scope: Scope = 'engaged') =>
    get<any>(`/api/dashboard/pnl-summary?year=${year}&scope=${scope}`),
  invoiceTimeline: () => get<any>('/api/dashboard/invoice-timeline'),
  fxConversions: () => get<any>('/api/dashboard/fx-conversions'),
  treasuryBridge: (asOf?: string) =>
    get<any>(`/api/dashboard/treasury-bridge${asOf ? `?as_of=${asOf}` : ''}`),
};

export const bankingAPI = {
  status: () => get<{ live: boolean; message: string }>('/api/banking/status'),
  aspsps: (country = 'FR') => get<any[]>(`/api/banking/aspsps?country=${country}`),
  connect: (aspsp_name: string) =>
    post<any>('/api/banking/connect', { aspsp_name }),
  createSession: (code: string, state?: string) =>
    post<any>('/api/banking/sessions', { code, state }),
  selectAccounts: (accounts: Record<string, unknown>[]) =>
    post<any[]>('/api/banking/connections/select', { accounts }),
  connections: () => get<any[]>('/api/banking/connections'),
  sync: () => post<any>('/api/banking/sync'),
  disconnect: (id: number) => del(`/api/banking/connections/${id}`),
};
