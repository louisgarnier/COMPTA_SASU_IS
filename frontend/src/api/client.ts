/**
 * Client API front LGC — communication avec le backend FastAPI local.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!response.ok) {
    const err = await response
      .json()
      .catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(err.detail || `HTTP ${response.status}`);
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

export const clientsAPI = {
  list: () => get<any[]>('/api/clients'),
  create: (b: Record<string, unknown>) => post<any>('/api/clients', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/clients/${id}`, b),
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
};

export const categoriesAPI = {
  list: () => get<any[]>('/api/categories'),
  create: (b: Record<string, unknown>) => post<any>('/api/categories', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/categories/${id}`, b),
  listRules: () => get<any[]>('/api/category-rules'),
  createRule: (b: Record<string, unknown>) => post<any>('/api/category-rules', b),
  updateRule: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/category-rules/${id}`, b),
  deleteRule: (id: number) => del(`/api/category-rules/${id}`),
};

export const treasuryAPI = {
  get: () => get<any>('/api/treasury'),
  pnl: (year = 2026) => get<any>(`/api/pnl?year=${year}`),
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
  get: (year = 2026, startingCash?: number) =>
    get<any>(
      `/api/forecast?year=${year}` +
        (startingCash !== undefined ? `&starting_cash_eur=${startingCash}` : ''),
    ),
  save: (b: Record<string, unknown>) => put<any>('/api/forecast', b),
};

export const invoicesAPI = {
  list: () => get<any[]>('/api/invoices'),
  get: (id: number) => get<any>(`/api/invoices/${id}`),
  create: (b: Record<string, unknown>) => post<any>('/api/invoices', b),
  update: (id: number, b: Record<string, unknown>) =>
    patch<any>(`/api/invoices/${id}`, b),
  generatePdf: (id: number) => post<{ pdf_path: string }>(`/api/invoices/${id}/pdf`),
  downloadUrl: (id: number) => `${API_BASE_URL}/api/invoices/${id}/download`,
};

export const bankingAPI = {
  status: () => get<{ live: boolean; message: string }>('/api/banking/status'),
  aspsps: (country = 'FR') => get<any[]>(`/api/banking/aspsps?country=${country}`),
  connect: (aspsp_name: string) =>
    post<any>('/api/banking/connect', { aspsp_name }),
  createSession: (code: string) => post<any>('/api/banking/sessions', { code }),
  connections: () => get<any[]>('/api/banking/connections'),
  sync: () => post<any>('/api/banking/sync'),
};
