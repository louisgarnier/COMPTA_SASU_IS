'use client';

import { useEffect, useMemo, useState } from 'react';
import { forecastAPI, clientsAPI, fxAPI, treasuryAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Empty } from '@/components/ui';
import { eur, pct, MONTH_LABELS } from '@/lib/format';

// Aujourd'hui (réf. projet) — pilote les mois écoulés vs à venir.
const TODAY = new Date('2026-07-03T00:00:00');
const CUR_YEAR = TODAY.getFullYear();
const CUR_MONTH = TODAY.getMonth() + 1; // 1..12
const YEARS = [CUR_YEAR, CUR_YEAR + 1, CUR_YEAR + 2];

type Client = {
  id: number;
  code: string;
  legal_name: string;
  currency: string;
  tjh: string | number;
  billing_mode: string; // 'tjm' | 'thm'
  default_hours_per_day: string | number;
};

type ForecastInput = {
  month: string;
  client_id: number;
  days: number | string;
  hours: number | string;
  rate: number | string;
  rate_unit: string;
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
  projection: { months: ProjectionMonth[]; totals: { revenue_eur: string; charges_eur: string } };
  is: {
    base_eur: string; threshold_eur: string; low_rate: string; high_rate: string;
    is_low_eur: string; is_high_eur: string; is_total_eur: string;
  };
};

type Cell = { days: string; hours: string; rate: string };

const num = (v: string | number | null | undefined) => {
  const n = parseFloat(String(v ?? '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
};
const fmt = (n: number) =>
  n ? n.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) : '0';

function monthLabel(month: string): string {
  return MONTH_LABELS[parseInt(month.slice(5, 7), 10) - 1] ?? month;
}
function cellKey(clientId: number, month: string): string {
  return `${clientId}-${month}`;
}

// Mois de l'année sélectionnée + éditabilité (mois écoulés grisés en année courante).
function monthsForYear(year: number): { key: string; label: string; editable: boolean }[] {
  return Array.from({ length: 12 }, (_, i) => {
    const m = i + 1;
    const editable = year > CUR_YEAR || (year === CUR_YEAR && m >= CUR_MONTH);
    return { key: `${year}-${String(m).padStart(2, '0')}`, label: MONTH_LABELS[i], editable };
  });
}

export default function ForecastPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [year, setYear] = useState(CUR_YEAR);
  const [data, setData] = useState<ForecastData | null>(null);
  const [grid, setGrid] = useState<Record<string, Cell>>({});
  const [fx, setFx] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const months = useMemo(() => monthsForYear(year), [year]);

  function hpd(c: Client): number {
    const h = num(c.default_hours_per_day);
    return h > 0 ? h : 8;
  }

  function buildGrid(clientList: Client[], inputs: ForecastInput[], ms: typeof months): Record<string, Cell> {
    const byKey: Record<string, ForecastInput> = {};
    inputs.forEach((i) => (byKey[cellKey(i.client_id, i.month)] = i));
    const next: Record<string, Cell> = {};
    clientList.forEach((c) => {
      ms.forEach((m) => {
        const ex = byKey[cellKey(c.id, m.key)];
        next[cellKey(c.id, m.key)] = {
          days: ex ? String(ex.days ?? '') : '',
          hours: ex ? String(ex.hours ?? '') : '',
          rate: ex ? String(ex.rate ?? '') : String(c.tjh ?? ''),
        };
      });
    });
    return next;
  }

  async function load(y: number) {
    setLoading(true);
    setError('');
    try {
      // Trésorerie de départ = vrai solde consolidé actuel → le déroulé cumulé
      // démarre au solde réel (et non à 0). Non bloquant : si l'appel tréso
      // échoue, on démarre à 0 plutôt que de vider tout le forecast.
      let startingCash = 0;
      try {
        const treasury = await treasuryAPI.get();
        startingCash = num(treasury?.total_eur ?? treasury?.bank_total_eur ?? 0);
      } catch {
        startingCash = 0;
      }
      const [clientList, forecast, fxList] = await Promise.all([
        clientsAPI.list() as Promise<Client[]>,
        forecastAPI.get(y, startingCash) as Promise<ForecastData>,
        fxAPI.list() as Promise<{ currency: string; rate: string }[]>,
      ]);
      const fxMap: Record<string, number> = { EUR: 1 };
      fxList.forEach((r) => (fxMap[r.currency] = num(r.rate)));
      setClients(clientList);
      setData(forecast);
      setFx(fxMap);
      setGrid(buildGrid(clientList, forecast.inputs ?? [], monthsForYear(y)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  // Édition d'une cellule. En THM, jours ⇄ heures liés (l'un recalcule l'autre).
  function editCell(c: Client, month: string, field: 'days' | 'hours' | 'rate', value: string) {
    const key = cellKey(c.id, month);
    setGrid((prev) => {
      const cur = prev[key] ?? { days: '', hours: '', rate: '' };
      const next = { ...cur, [field]: value };
      const h = hpd(c);
      if (field === 'days') next.hours = value === '' ? '' : String(+(num(value) * h).toFixed(2));
      if (field === 'hours') next.days = value === '' ? '' : String(+(num(value) / h).toFixed(2));
      return { ...prev, [key]: next };
    });
  }

  async function toggleMode(c: Client, mode: 'tjm' | 'thm') {
    if (c.billing_mode === mode) return;
    setClients((prev) => prev.map((x) => (x.id === c.id ? { ...x, billing_mode: mode } : x)));
    try {
      await clientsAPI.update(c.id, { billing_mode: mode });
      // Repropage le nouveau mode aux prévisions existantes (mois ≥ courant) puis
      // recharge la grille — sinon les lignes gardaient l'ancien mode/montant.
      await clientsAPI.reprice(c.id);
      setStatus('✅ Mode mis à jour et prévisions recalculées');
      await load(year);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function save() {
    setStatus('Enregistrement…');
    try {
      const inputs: ForecastInput[] = [];
      clients.forEach((c) => {
        const isHour = c.billing_mode === 'thm';
        months.forEach((m) => {
          if (!m.editable) return;
          const cell = grid[cellKey(c.id, m.key)];
          if (!cell) return;
          const driver = isHour ? num(cell.hours) : num(cell.days);
          if (driver <= 0) return;
          inputs.push({
            month: m.key,
            client_id: c.id,
            rate_unit: isHour ? 'hour' : 'day',
            days: num(cell.days),
            hours: num(cell.hours),
            rate: num(cell.rate) || 0,
            note: '',
          });
        });
      });
      const updated = (await forecastAPI.save({ year, inputs })) as ForecastData;
      setData(updated);
      setGrid(buildGrid(clients, updated.inputs ?? [], months));
      setStatus('✅ Enregistré');
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  const maxCash = useMemo(() => {
    if (!data) return 1;
    const vals = data.projection.months.map((m) => Math.abs(num(m.cumulative_cash_eur)));
    return Math.max(1, ...vals);
  }, [data]);

  if (loading) {
    return (
      <div>
        <PageTitle title="Forecast" subtitle="Projection revenus, tréso & estimation IS" />
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div>
        <PageTitle title="Forecast" subtitle="Projection revenus, tréso & estimation IS" />
        <Empty>Erreur de chargement : {error}</Empty>
      </div>
    );
  }

  const is = data!.is;
  const totals = data!.projection.totals;
  const projMonths = data!.projection.months;

  return (
    <div>
      <PageTitle
        title="Forecast"
        subtitle="Projection revenus, tréso & estimation IS — facturation TJM (jour) ou THM (heure)"
        action={
          <button
            onClick={save}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Enregistrer
          </button>
        }
      />

      {/* Sélecteur d'année */}
      <div className="mb-4 flex items-center gap-3">
        <span className="text-sm font-medium text-[var(--muted)]">Année</span>
        <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
          {YEARS.map((y) => (
            <button
              key={y}
              onClick={() => setYear(y)}
              className={`border-r border-[var(--border)] px-4 py-1.5 text-sm font-semibold last:border-r-0 ${
                y === year ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--text)] hover:bg-gray-50'
              }`}
            >
              {y}
            </button>
          ))}
        </div>
        <span className="text-xs text-[var(--muted)]">
          {year === CUR_YEAR ? 'Année en cours — mois écoulés grisés.' : 'Année complète (12 mois).'}
        </span>
      </div>
      {status && <p className="mb-4 text-sm text-[var(--muted)]">{status}</p>}

      {/* KPI */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={`CA projeté ${year}`} value={eur(totals.revenue_eur)} tone="pos" />
        <StatCard label="Charges projetées" value={eur(totals.charges_eur)} tone="neg" />
        <StatCard label="Base IS" value={eur(is.base_eur)} />
        <Card>
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">IS estimé</div>
          <div className="tabular mt-2 text-2xl font-semibold text-[var(--neg)]">{eur(is.is_total_eur)}</div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {pct(is.low_rate)} jusqu&apos;à {eur(is.threshold_eur)} + {pct(is.high_rate)} au-delà
          </div>
        </Card>
      </div>

      {/* Repère clients */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-[var(--muted)]">Clients</span>
        {clients.map((c) => (
          <span key={c.id} className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs font-medium">
            {c.code} · {c.currency}
          </span>
        ))}
        <a href="/clients" className="rounded-lg border border-dashed border-[var(--accent)] px-2.5 py-1 text-xs font-medium text-[var(--accent)]">
          + Ajouter un client
        </a>
      </div>

      {/* Une table par client */}
      {clients.length === 0 ? (
        <Empty>Aucun client. Ajoutez un client pour saisir des prévisions.</Empty>
      ) : (
        <div className="flex flex-col gap-5">
          {clients.map((c) => (
            <ClientGrid
              key={c.id}
              client={c}
              months={months}
              grid={grid}
              fx={fx}
              hpd={hpd(c)}
              onEdit={editCell}
              onMode={toggleMode}
            />
          ))}
        </div>
      )}

      {/* Déroulé tréso */}
      <Card className="mt-6">
        <div className="mb-3 text-sm font-semibold">Déroulé tréso — {year}</div>
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
              {projMonths.map((m) => {
                const cash = num(m.cumulative_cash_eur);
                const net = num(m.net_eur);
                const neg = cash < 0;
                return (
                  <tr key={m.month} className="border-t border-[var(--border)]">
                    <td className="py-2 pr-3">
                      {monthLabel(m.month)}
                      {m.is_forecast && (
                        <span className="ml-2 rounded bg-[var(--border)]/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--muted)]">
                          prév.
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">{eur(m.revenue_eur)}</td>
                    <td className={`px-3 py-2 text-right text-[var(--neg)] ${m.is_forecast ? 'italic opacity-70' : ''}`}>
                      {eur(m.charges_eur)}
                    </td>
                    <td className={`px-3 py-2 text-right ${net < 0 ? 'text-[var(--neg)]' : 'text-[var(--pos)]'}`}>
                      {eur(m.net_eur)}
                    </td>
                    <td className={`px-3 py-2 text-right font-medium ${neg ? 'text-[var(--neg)]' : ''}`}>
                      {eur(m.cumulative_cash_eur)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="h-3 w-full rounded bg-[var(--border)]/40">
                        <div
                          className={`h-3 rounded ${neg ? 'bg-[var(--neg)]' : 'bg-[var(--accent)]'}`}
                          style={{ width: `${(Math.abs(cash) / maxCash) * 100}%` }}
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

// --------------------------------------------------------------------------- //
// Table d'un client                                                           //
// --------------------------------------------------------------------------- //

function ClientGrid({
  client, months, grid, fx, hpd, onEdit, onMode,
}: {
  client: Client;
  months: { key: string; label: string; editable: boolean }[];
  grid: Record<string, Cell>;
  fx: Record<string, number>;
  hpd: number;
  onEdit: (c: Client, month: string, field: 'days' | 'hours' | 'rate', value: string) => void;
  onMode: (c: Client, mode: 'tjm' | 'thm') => void;
}) {
  const isHour = client.billing_mode === 'thm';
  const rate = fx[client.currency] ?? 1;
  const cur = client.currency;

  // Montant natif d'une cellule selon le mode.
  const cellAmount = (cell?: Cell): number => {
    if (!cell) return 0;
    return isHour ? num(cell.hours) * num(cell.rate) : num(cell.days) * num(cell.rate);
  };

  const tot = { days: 0, hours: 0, amount: 0, eur: 0 };
  months.forEach((m) => {
    const cell = grid[cellKey(client.id, m.key)];
    tot.days += num(cell?.days);
    tot.hours += num(cell?.hours);
    const a = cellAmount(cell);
    tot.amount += a;
    tot.eur += a * rate;
  });

  const input = (m: { key: string; editable: boolean }, field: 'days' | 'hours' | 'rate') => {
    const cell = grid[cellKey(client.id, m.key)];
    return (
      <input
        type="number"
        step="any"
        disabled={!m.editable}
        aria-label={`${client.code} ${m.key} ${field}`}
        value={cell?.[field] ?? ''}
        onChange={(e) => onEdit(client, m.key, field, e.target.value)}
        className={`w-16 rounded-md border px-2 py-1 text-right outline-none focus:border-[var(--accent)] ${
          field !== 'rate' && (isHour) ? 'border-[var(--accent)]/40 bg-[var(--accent)]/5' : 'border-[var(--border)]'
        } disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-[var(--muted)]`}
      />
    );
  };

  const derivedCell = (v: number) => (
    <span className="inline-block w-16 rounded-md bg-gray-50 px-2 py-1 text-right text-[var(--muted)]">
      {fmt(v)}
    </span>
  );

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">
          {client.legal_name} <span className="text-[var(--muted)]">· {client.code} · {cur}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
          <span>Facturation</span>
          <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
            {(['tjm', 'thm'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => onMode(client, mode)}
                className={`border-r border-[var(--border)] px-2.5 py-1 font-semibold last:border-r-0 ${
                  client.billing_mode === mode ? 'bg-[var(--accent)] text-white' : 'bg-white hover:bg-gray-50'
                }`}
              >
                {mode === 'tjm' ? 'TJM · jour' : 'THM · heure'}
              </button>
            ))}
          </div>
          <span>· h/j <b>{hpd}</b> · FX <b>{rate}</b> <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700">auto</span></span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[840px] text-sm tabular">
          <thead>
            <tr className="text-xs uppercase text-[var(--muted)]">
              <th className="sticky left-0 bg-white py-1 pr-3 text-left font-medium">Champ</th>
              {months.map((m) => (
                <th key={m.key} className={`px-1 py-1 text-right font-medium ${!m.editable ? 'opacity-40' : ''}`}>
                  {m.label}
                </th>
              ))}
              <th className="bg-gray-50 px-2 py-1 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {/* Jours */}
            <tr className="border-t border-[var(--border)]">
              <td className="sticky left-0 bg-white py-1 pr-3 text-[var(--muted)]">
                Jours {!isHour ? '✎' : <span className="text-[var(--accent)]">⇅</span>}
              </td>
              {months.map((m) => (
                <td key={m.key} className="px-1 py-1 text-right">{input(m, 'days')}</td>
              ))}
              <td className="bg-gray-50 px-2 py-1 text-right">{fmt(tot.days)}</td>
            </tr>
            {/* Heures */}
            <tr className="border-t border-[var(--border)]">
              <td className="sticky left-0 bg-white py-1 pr-3 text-[var(--muted)]">
                Heures {isHour ? <span className="text-[var(--accent)]">✎ ⇅</span> : <span title="verrouillé = jours × h/j">🔒</span>}
              </td>
              {months.map((m) => (
                <td key={m.key} className="px-1 py-1 text-right">
                  {isHour ? input(m, 'hours') : derivedCell(num(grid[cellKey(client.id, m.key)]?.days) * hpd)}
                </td>
              ))}
              <td className="bg-gray-50 px-2 py-1 text-right text-[var(--muted)]">{fmt(tot.hours)}</td>
            </tr>
            {/* Taux */}
            <tr className="border-t border-[var(--border)]">
              <td className="sticky left-0 bg-white py-1 pr-3 text-[var(--muted)]">
                Taux ({cur === 'EUR' ? '€' : '$'}/{isHour ? 'h' : 'j'})
              </td>
              {months.map((m) => (
                <td key={m.key} className="px-1 py-1 text-right">{input(m, 'rate')}</td>
              ))}
              <td className="bg-gray-50 px-2 py-1 text-right text-[var(--muted)]">—</td>
            </tr>
            {/* Montant (facture) */}
            <tr className="border-t border-[var(--border)] bg-[var(--accent)]/5">
              <td className="sticky left-0 bg-[#fbfbfe] py-1 pr-3 font-medium">
                Montant {cur} <span className="ml-1 rounded bg-[var(--accent)]/10 px-1 py-0.5 text-[9px] font-bold uppercase text-[var(--accent)]">facture</span>
              </td>
              {months.map((m) => (
                <td key={m.key} className="px-1 py-1 text-right font-semibold">
                  {fmt(cellAmount(grid[cellKey(client.id, m.key)]))}
                </td>
              ))}
              <td className="bg-gray-50 px-2 py-1 text-right font-semibold">{fmt(tot.amount)}</td>
            </tr>
            {/* EUR */}
            <tr className="border-t border-[var(--border)]">
              <td className="sticky left-0 bg-white py-1 pr-3 text-[var(--muted)]">€ (× {rate})</td>
              {months.map((m) => (
                <td key={m.key} className="px-1 py-1 text-right font-bold">
                  {fmt(cellAmount(grid[cellKey(client.id, m.key)]) * rate)}
                </td>
              ))}
              <td className="bg-gray-50 px-2 py-1 text-right font-bold">{fmt(tot.eur)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-xs text-[var(--muted)]">
        {isHour
          ? 'THM : Jours ⇅ Heures liés (saisir l’un recalcule l’autre) · Montant = heures × taux.'
          : 'TJM : Jours éditable (16,5 possible), Heures 🔒 calculées · Montant = jours × taux.'}
      </div>
    </Card>
  );
}
