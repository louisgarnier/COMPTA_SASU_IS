'use client';

import { useEffect, useMemo, useState } from 'react';
import { forecastAPI, clientsAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Empty } from '@/components/ui';
import { eur, pct, MONTH_LABELS } from '@/lib/format';

const YEAR = 2026;
// Mois prévisionnels : Juil → Déc 2026
const FORECAST_MONTHS = ['2026-07', '2026-08', '2026-09', '2026-10', '2026-11', '2026-12'];

type Client = { id: number; code: string; legal_name: string; currency: string; tjh: string };

type ForecastInput = {
  id?: number;
  month: string;
  client_id: number;
  days: number | string;
  rate: number | string;
  fx_rate: number | string;
  note?: string;
};

type ProjectionMonth = {
  month: string;
  revenue_eur: string;
  charges_eur: string;
  net_eur: string;
  cumulative_cash_eur: string;
  is_forecast: boolean;
};

type ForecastData = {
  inputs: ForecastInput[];
  projection: {
    months: ProjectionMonth[];
    totals: { revenue_eur: string; charges_eur: string };
  };
  is: {
    base_eur: string;
    threshold_eur: string;
    low_rate: string;
    high_rate: string;
    is_low_eur: string;
    is_high_eur: string;
    is_total_eur: string;
  };
};

// Libellé "Juil" à partir d'un mois 'YYYY-MM'
function monthLabel(month: string): string {
  const idx = parseInt(month.slice(5, 7), 10) - 1;
  return MONTH_LABELS[idx] ?? month;
}

// Clé cellule = client + mois
function cellKey(clientId: number, month: string): string {
  return `${clientId}-${month}`;
}

type Cell = { days: string; rate: string; fx_rate: string; note?: string };

export default function ForecastPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [data, setData] = useState<ForecastData | null>(null);
  const [grid, setGrid] = useState<Record<string, Cell>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  // Construit la matrice éditable à partir des inputs existants + valeurs par défaut client
  function buildGrid(clientList: Client[], inputs: ForecastInput[]): Record<string, Cell> {
    const byKey: Record<string, ForecastInput> = {};
    inputs.forEach((i) => (byKey[cellKey(i.client_id, i.month)] = i));
    const next: Record<string, Cell> = {};
    clientList.forEach((c) => {
      FORECAST_MONTHS.forEach((m) => {
        const existing = byKey[cellKey(c.id, m)];
        next[cellKey(c.id, m)] = {
          days: existing ? String(existing.days ?? '') : '',
          rate: existing ? String(existing.rate ?? '') : String(c.tjh ?? ''),
          fx_rate: existing ? String(existing.fx_rate ?? '') : '1',
          note: existing?.note ?? '',
        };
      });
    });
    return next;
  }

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [clientList, forecast] = await Promise.all([
        clientsAPI.list() as Promise<Client[]>,
        forecastAPI.get(YEAR) as Promise<ForecastData>,
      ]);
      setClients(clientList);
      setData(forecast);
      setGrid(buildGrid(clientList, forecast.inputs ?? []));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateCell(clientId: number, month: string, field: keyof Cell, value: string) {
    const key = cellKey(clientId, month);
    setGrid((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }));
  }

  async function save() {
    setStatus('Enregistrement…');
    try {
      // On envoie toute cellule avec au moins un nombre de jours saisi
      const inputs: ForecastInput[] = [];
      clients.forEach((c) => {
        FORECAST_MONTHS.forEach((m) => {
          const cell = grid[cellKey(c.id, m)];
          if (!cell) return;
          const days = parseFloat(cell.days);
          if (!Number.isFinite(days) || days === 0) return;
          inputs.push({
            month: m,
            client_id: c.id,
            days,
            rate: parseFloat(cell.rate) || 0,
            fx_rate: parseFloat(cell.fx_rate) || 1,
            note: cell.note || '',
          });
        });
      });
      const updated = (await forecastAPI.save({ year: YEAR, inputs })) as ForecastData;
      setData(updated);
      setGrid(buildGrid(clients, updated.inputs ?? []));
      setStatus('✅ Enregistré');
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  // Échelle pour les barres de tréso (valeur absolue max)
  const maxCash = useMemo(() => {
    if (!data) return 1;
    const vals = data.projection.months.map((m) => Math.abs(parseFloat(m.cumulative_cash_eur) || 0));
    return Math.max(1, ...vals);
  }, [data]);

  if (loading) {
    return (
      <div>
        <PageTitle title="Forecast" subtitle="Projection revenus, tréso & estimation IS — 2026" />
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <PageTitle title="Forecast" subtitle="Projection revenus, tréso & estimation IS — 2026" />
        <Empty>Erreur de chargement : {error}</Empty>
      </div>
    );
  }

  const is = data!.is;
  const totals = data!.projection.totals;
  const months = data!.projection.months;

  return (
    <div>
      <PageTitle
        title="Forecast"
        subtitle="Projection revenus, tréso & estimation IS — 2026"
        action={
          <button
            onClick={save}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Enregistrer
          </button>
        }
      />
      {status && <p className="mb-4 text-sm text-[var(--muted)]">{status}</p>}

      {/* Indicateurs clés */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="CA projeté" value={eur(totals.revenue_eur)} tone="pos" />
        <StatCard label="Charges projetées" value={eur(totals.charges_eur)} tone="neg" />
        <StatCard label="Base IS" value={eur(is.base_eur)} />
        <Card>
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">IS estimé</div>
          <div className="tabular mt-2 text-2xl font-semibold text-[var(--neg)]">
            {eur(is.is_total_eur)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {pct(is.low_rate)} jusqu&apos;à {eur(is.threshold_eur)} + {pct(is.high_rate)} au-delà
          </div>
        </Card>
      </div>

      {/* Saisie prévisionnelle */}
      <Card className="mb-6">
        <div className="mb-3 text-sm font-semibold">Saisie prévisionnelle</div>
        {clients.length === 0 ? (
          <Empty>Aucun client. Ajoutez un client pour saisir des prévisions.</Empty>
        ) : (
          <div className="flex flex-col gap-6">
            {clients.map((c) => (
              <div key={c.id}>
                <div className="mb-2 text-sm font-medium">
                  {c.legal_name}{' '}
                  <span className="text-[var(--muted)]">
                    · {c.code} · {c.currency}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm tabular">
                    <thead>
                      <tr className="text-left text-xs uppercase text-[var(--muted)]">
                        <th className="py-1 pr-3 font-medium">Champ</th>
                        {FORECAST_MONTHS.map((m) => (
                          <th key={m} className="px-2 py-1 text-right font-medium">
                            {monthLabel(m)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(['days', 'rate', 'fx_rate'] as const).map((field) => (
                        <tr key={field} className="border-t border-[var(--border)]">
                          <td className="py-1 pr-3 text-[var(--muted)]">
                            {field === 'days' ? 'Jours' : field === 'rate' ? 'TJH' : 'FX'}
                          </td>
                          {FORECAST_MONTHS.map((m) => (
                            <td key={m} className="px-1 py-1">
                              <input
                                type="number"
                                step="any"
                                aria-label={`${c.code} ${monthLabel(m)} ${field}`}
                                value={grid[cellKey(c.id, m)]?.[field] ?? ''}
                                onChange={(e) => updateCell(c.id, m, field, e.target.value)}
                                className="w-full rounded-md border border-[var(--border)] px-2 py-1 text-right outline-none focus:border-[var(--accent)]"
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Déroulé tréso */}
      <Card>
        <div className="mb-3 text-sm font-semibold">Déroulé tréso</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="text-left text-xs uppercase text-[var(--muted)]">
                <th className="py-2 pr-3 font-medium">Mois</th>
                <th className="px-3 py-2 text-right font-medium">Revenus</th>
                <th className="px-3 py-2 text-right font-medium">Charges</th>
                <th className="px-3 py-2 text-right font-medium">Net</th>
                <th className="px-3 py-2 text-right font-medium">Tréso cumulée</th>
                <th className="w-1/3 px-3 py-2 font-medium">Évolution</th>
              </tr>
            </thead>
            <tbody>
              {months.map((m) => {
                const cash = parseFloat(m.cumulative_cash_eur) || 0;
                const net = parseFloat(m.net_eur) || 0;
                const width = `${(Math.abs(cash) / maxCash) * 100}%`;
                const neg = cash < 0;
                return (
                  <tr key={m.month} className="border-t border-[var(--border)]">
                    <td className="py-2 pr-3">
                      {monthLabel(m.month)}
                      {m.is_forecast && (
                        <span
                          className="ml-2 rounded bg-[var(--border)]/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--muted)]"
                          title="Charges estimées (mois en cours au prorata / mois à venir en moyenne)"
                        >
                          prév.
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">{eur(m.revenue_eur)}</td>
                    <td
                      className={`px-3 py-2 text-right text-[var(--neg)] ${m.is_forecast ? 'italic opacity-70' : ''}`}
                    >
                      {eur(m.charges_eur)}
                    </td>
                    <td
                      className={`px-3 py-2 text-right ${net < 0 ? 'text-[var(--neg)]' : 'text-[var(--pos)]'}`}
                    >
                      {eur(m.net_eur)}
                    </td>
                    <td
                      className={`px-3 py-2 text-right font-medium ${neg ? 'text-[var(--neg)]' : ''}`}
                    >
                      {eur(m.cumulative_cash_eur)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="h-3 w-full rounded bg-[var(--border)]/40">
                        <div
                          className={`h-3 rounded ${neg ? 'bg-[var(--neg)]' : 'bg-[var(--accent)]'}`}
                          style={{ width }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
