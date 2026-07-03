'use client';

import { useEffect, useState } from 'react';
import { treasuryAPI, investmentsAPI, forecastAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { eur, money, dateFR, MONTH_LABELS } from '@/lib/format';
import { BalanceDocsModal } from '@/components/BalanceDocsModal';

type Account = {
  account_uid: string;
  name: string;
  provider: string;
  currency: string;
  balance: string | number;
};

type Treasury = {
  as_of?: string | null;
  accounts: Account[];
  bank_total_eur: string | number;
  investments_total_eur: string | number;
  total_eur: string | number;
};

type CcyMap = Record<string, string | number>;

type PnlMonth = {
  month: string;
  revenue_eur: string | number;
  charges_eur: string | number;
  result_eur: string | number;
  revenue_by_currency?: CcyMap;
};

type Pnl = {
  year: number;
  currencies?: string[];
  currencies_all?: string[];
  months: PnlMonth[];
  totals: {
    revenue_eur: string | number;
    charges_eur: string | number;
    result_eur: string | number;
    revenue_by_currency?: CcyMap;
    revenue_native_by_currency?: CcyMap;
    charges_by_currency?: CcyMap;
    charges_native_by_currency?: CcyMap;
  };
};

// Palette par devise pour l'empilement du graphe P&L.
const CCY_COLORS: Record<string, string> = {
  EUR: '#16a34a',
  USD: '#2563eb',
  CAD: '#f59e0b',
  GBP: '#8b5cf6',
};
const ccyColor = (c: string, i: number) =>
  CCY_COLORS[c] ?? ['#16a34a', '#2563eb', '#f59e0b', '#8b5cf6', '#ec4899'][i % 5];

const todayISO = () => new Date().toISOString().slice(0, 10);

// Montant compact pour affichage sur les barres (ex: 8704 → "8,7k").
const kEur = (v: string | number | null | undefined): string => {
  const n = Math.abs(typeof v === 'string' ? parseFloat(v) : v ?? 0);
  if (!n) return '';
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace('.', ',') + 'k';
  return String(Math.round(n));
};

type InvestmentsSummary = {
  total_opening_value_eur: string | number;
  total_current_value_eur: string | number;
  gain_eur: string | number;
};

type ForecastMonth = {
  month: string;
  revenue_eur: string | number;
  charges_eur: string | number;
  charges_actual_eur?: string | number;
  charges_forecast_eur?: string | number;
  net_eur: string | number;
  cumulative_cash_eur: string | number;
  is_forecast?: boolean;
};

type Forecast = {
  inputs: unknown[];
  projection: {
    months: ForecastMonth[];
    totals: { revenue_eur: string | number; charges_eur: string | number };
  };
  is: {
    base_eur: string | number;
    threshold_eur: string | number;
    low_rate: string | number;
    high_rate: string | number;
    is_low_eur: string | number;
    is_high_eur: string | number;
    is_total_eur: string | number;
  };
};

const num = (v: string | number | null | undefined): number => {
  const n = typeof v === 'string' ? parseFloat(v) : v ?? 0;
  return Number.isFinite(n as number) ? (n as number) : 0;
};

export default function DashboardPage() {
  const [treasury, setTreasury] = useState<Treasury | null>(null);
  const [pnl, setPnl] = useState<Pnl | null>(null);
  const [invest, setInvest] = useState<InvestmentsSummary | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [asOf, setAsOf] = useState<string>(todayISO());
  const [docsOpen, setDocsOpen] = useState(false);

  // P&L / investissements / forecast : chargés une fois.
  useEffect(() => {
    Promise.all([treasuryAPI.pnl(2026), investmentsAPI.summary(), forecastAPI.get(2026)])
      .then(([p, i, f]) => {
        setPnl(p);
        setInvest(i);
        setForecast(f);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  // Trésorerie : rechargée à chaque changement de date de valorisation.
  useEffect(() => {
    treasuryAPI
      .get(asOf)
      .then(setTreasury)
      .catch((e) => setError((e as Error).message));
  }, [asOf]);

  if (loading) {
    return (
      <div>
        <PageTitle title="Dashboard" subtitle="Vue d'ensemble tréso 2026" />
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <PageTitle title="Dashboard" subtitle="Vue d'ensemble tréso 2026" />
        <p className="text-sm text-[var(--neg)]">❌ Erreur : {error}</p>
      </div>
    );
  }

  const gain = num(invest?.gain_eur);
  const pnlResult = num(pnl?.totals.result_eur);
  const ccys = pnl?.currencies ?? [];
  const totalsByCcy = pnl?.totals.revenue_by_currency ?? {};
  const nativeByCcy = pnl?.totals.revenue_native_by_currency ?? {};
  const flowCcys = pnl?.currencies_all ?? ccys;
  const chargesByCcy = pnl?.totals.charges_by_currency ?? {};
  const chargesNativeByCcy = pnl?.totals.charges_native_by_currency ?? {};

  // Échelle du graphe P&L : max valeur absolue sur revenus (total mois) / charges
  const pnlMax = Math.max(
    1,
    ...(pnl?.months ?? []).flatMap((m) => [
      Math.abs(num(m.revenue_eur)),
      Math.abs(num(m.charges_eur)),
    ]),
  );

  const projMonths = forecast?.projection.months ?? [];

  // Géométrie du combo « Prévision tréso » : barres = Δ net mensuel (couleur
  // par signe), ligne = cash cumulé. UN SEUL axe € (cumulé = somme des Δ).
  const CW = 360;
  const CH = 150;
  const CPAD = 16;
  const chart = (() => {
    if (projMonths.length === 0) return null;
    const nets = projMonths.map((m) => num(m.net_eur));
    const cums = projMonths.map((m) => num(m.cumulative_cash_eur));
    const dMin = Math.min(0, ...nets, ...cums);
    const dMax = Math.max(0, ...nets, ...cums);
    const span = dMax - dMin || 1;
    const yFor = (v: number) => CH - CPAD - ((v - dMin) / span) * (CH - 2 * CPAD);
    const slotW = CW / projMonths.length;
    const barW = slotW * 0.46;
    const zeroY = yFor(0);
    const lastRealIdx = projMonths.reduce((acc, m, i) => (m.is_forecast ? acc : i), 0);
    const points = projMonths.map((m, i) => ({
      x: i * slotW + slotW / 2,
      y: yFor(num(m.cumulative_cash_eur)),
      forecast: !!m.is_forecast,
    }));
    return { nets, cums, dMin, dMax, yFor, slotW, barW, zeroY, lastRealIdx, points };
  })();

  return (
    <div className="flex flex-col gap-8">
      <PageTitle title="Dashboard" subtitle="Vue d'ensemble tréso 2026" />

      {/* Statistiques principales */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Trésorerie totale" value={eur(treasury?.total_eur)} tone="pos" />
        <StatCard label="Solde banques" value={eur(treasury?.bank_total_eur)} />
        <StatCard
          label="Investissements"
          value={
            <div>
              <div>{eur(treasury?.investments_total_eur)}</div>
              <div className={`mt-1 text-xs font-medium ${gain >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
                {gain >= 0 ? '+' : ''}
                {eur(gain)}
              </div>
            </div>
          }
        />
        <StatCard label="Résultat P&L" value={eur(pnlResult)} tone={pnlResult >= 0 ? 'pos' : 'neg'} />
        <StatCard label="IS estimé" value={eur(forecast?.is.is_total_eur)} />
      </div>

      {/* P&L mensuel — revenus empilés par devise + charges */}
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">P&amp;L mensuel 2026</div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)]">
            {ccys.map((c, i) => (
              <span key={c} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ background: ccyColor(c, i) }}
                />
                Revenus {c}
              </span>
            ))}
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm bg-[var(--neg)]" /> Charges
            </span>
          </div>
        </div>
        <div className="flex items-end gap-2">
          {(pnl?.months ?? []).map((m, i) => {
            const chg = Math.abs(num(m.charges_eur));
            const byCcy = m.revenue_by_currency ?? {};
            return (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex w-full items-end justify-center gap-0.5" style={{ height: 175 }}>
                  {/* Barre revenus empilée par devise (montant en petit dans chaque segment) */}
                  <div className="flex w-1/2 flex-col justify-end" style={{ height: 175 }}>
                    {ccys.map((c, ci) => {
                      const v = num(byCcy[c]);
                      if (v <= 0) return null;
                      const h = (v / pnlMax) * 175;
                      return (
                        <div
                          key={c}
                          className="flex w-full items-center justify-center overflow-hidden first:rounded-t"
                          style={{ height: `${h}px`, background: ccyColor(c, ci) }}
                          title={`${MONTH_LABELS[i]} — ${c} : ${eur(v)}`}
                        >
                          {h >= 14 && (
                            <span className="text-[8px] font-semibold leading-none text-white tabular">
                              {kEur(v)}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {/* Barre charges (montant en petit au-dessus) */}
                  <div className="flex w-1/2 flex-col items-center justify-end" style={{ height: 175 }}>
                    {chg > 0 && (
                      <span className="mb-0.5 text-[8px] font-medium leading-none text-[var(--neg)] tabular">
                        {kEur(chg)}
                      </span>
                    )}
                    <div
                      className="w-full rounded-t bg-[var(--neg)]"
                      style={{ height: `${(chg / pnlMax) * 175}px` }}
                      title={`Charges ${eur(m.charges_eur)}`}
                    />
                  </div>
                </div>
                <div className="text-[10px] text-[var(--muted)]">{MONTH_LABELS[i]}</div>
              </div>
            );
          })}
        </div>
        {/* Détail par devise : revenus (+) et charges (−), montant natif → EUR */}
        <div className="mt-4 border-t border-[var(--border)] pt-3">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Par devise (2026)
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {flowCcys.map((c, i) => {
              const rev = num(totalsByCcy[c]);
              const chg = num(chargesByCcy[c]);
              return (
                <div
                  key={c}
                  className="rounded-lg border border-[var(--border)] px-3 py-2"
                >
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                    <span
                      className="inline-block h-3 w-3 rounded-sm"
                      style={{ background: ccyColor(c, i) }}
                    />
                    {c}
                  </div>
                  {rev > 0 && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-[var(--muted)]">Revenus</span>
                      <span className="text-right">
                        <span className="tabular font-medium text-[var(--pos)]">
                          {money(nativeByCcy[c], c)}
                        </span>
                        <span className="tabular block text-xs text-[var(--muted)]">
                          = {eur(totalsByCcy[c])}
                        </span>
                      </span>
                    </div>
                  )}
                  {chg < 0 && (
                    <div className="mt-1 flex items-center justify-between text-sm">
                      <span className="text-[var(--muted)]">Charges</span>
                      <span className="text-right">
                        <span className="tabular font-medium text-[var(--neg)]">
                          {money(chargesNativeByCcy[c], c)}
                        </span>
                        <span className="tabular block text-xs text-[var(--muted)]">
                          = {eur(chargesByCcy[c])}
                        </span>
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-end gap-4 text-sm">
            <span className="text-[var(--muted)]">
              Total revenus{' '}
              <span className="tabular font-medium text-[var(--text)]">{eur(pnl?.totals.revenue_eur)}</span>
            </span>
            <span className="text-[var(--muted)]">
              Charges <span className="tabular font-medium text-[var(--text)]">{eur(pnl?.totals.charges_eur)}</span>
            </span>
            <span className="text-[var(--muted)]">
              Résultat{' '}
              <span className={`tabular font-medium ${pnlResult >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
                {eur(pnlResult)}
              </span>
            </span>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Comptes */}
        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Comptes</div>
            <button
              onClick={() => setDocsOpen(true)}
              className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium hover:bg-gray-50"
            >
              📎 Justificatifs
            </button>
          </div>
          <div className="mb-3 flex items-center gap-2 text-xs text-[var(--muted)]">
            <label htmlFor="asof">Soldes au</label>
            <input
              id="asof"
              type="date"
              value={asOf}
              max={todayISO()}
              onChange={(e) => setAsOf(e.target.value || todayISO())}
              className="rounded-lg border border-[var(--border)] px-2 py-1 text-[var(--text)] outline-none focus:border-[var(--accent)]"
            />
            <span>({dateFR(asOf)})</span>
          </div>
          {treasury && treasury.accounts.length > 0 ? (
            <div className="flex flex-col divide-y divide-[var(--border)]">
              {treasury.accounts.map((a) => (
                <div key={a.account_uid} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{a.name}</span>
                    <Badge>{a.provider}</Badge>
                    <span className="text-xs text-[var(--muted)]">{a.currency}</span>
                  </div>
                  <span className="tabular text-sm font-medium">{money(a.balance, a.currency)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between py-2.5 text-sm font-semibold">
                <span>Total banques (EUR)</span>
                <span className="tabular">{eur(treasury.bank_total_eur)}</span>
              </div>
            </div>
          ) : (
            <Empty>Aucun compte connecté.</Empty>
          )}
        </Card>

        {/* Prévision tréso — combo : barres Δ net + ligne cash cumulé */}
        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Prévision tréso</div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--muted)]">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[var(--pos)]" /> Δ + (entrée)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[var(--neg)]" /> Δ − (sortie)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 bg-[var(--accent)]" /> Cash cumulé
              </span>
              <span className="text-[var(--muted)]">· pâle = prévision</span>
            </div>
          </div>
          {chart ? (
            <>
              <svg
                viewBox={`0 0 ${CW} ${CH}`}
                width="100%"
                height={CH}
                role="img"
                aria-label="Prévision de trésorerie : variation mensuelle et cash cumulé"
                preserveAspectRatio="none"
              >
                {/* Ligne zéro */}
                <line
                  x1={0}
                  x2={CW}
                  y1={chart.zeroY}
                  y2={chart.zeroY}
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                {/* Barres Δ net — split réel (plein) / prévision (pâle) */}
                {projMonths.map((m, i) => {
                  const net = num(m.net_eur);
                  const y0 = chart.zeroY;
                  const y1 = chart.yFor(net);
                  const x = i * chart.slotW + (chart.slotW - chart.barW) / 2;
                  const color = net >= 0 ? 'var(--pos)' : 'var(--neg)';
                  const act = Math.abs(num(m.charges_actual_eur));
                  const fc = Math.abs(num(m.charges_forecast_eur));
                  const solidFrac = act + fc > 0 ? act / (act + fc) : m.is_forecast ? 0 : 1;
                  const splitY = y0 + (y1 - y0) * solidFrac;
                  return (
                    <g key={m.month}>
                      {/* Part réelle (adjacente à zéro) */}
                      <rect
                        x={x}
                        y={Math.min(y0, splitY)}
                        width={chart.barW}
                        height={Math.abs(splitY - y0)}
                        fill={color}
                        rx={1}
                      />
                      {/* Part prévisionnelle (au bout, pâle) */}
                      <rect
                        x={x}
                        y={Math.min(splitY, y1)}
                        width={chart.barW}
                        height={Math.abs(y1 - splitY)}
                        fill={color}
                        fillOpacity={0.32}
                        rx={1}
                      />
                      <title>
                        {`${MONTH_LABELS[i]} — Δ ${eur(net)}${m.is_forecast ? ` (réel ${eur(-act)} + prév. ${eur(-fc)})` : ''}\nCumulé ${eur(m.cumulative_cash_eur)}`}
                      </title>
                    </g>
                  );
                })}
                {/* Ligne cash cumulé : pleine (réel) puis pointillés (prévision) */}
                <polyline
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  strokeLinejoin="round"
                  points={chart.points
                    .slice(0, chart.lastRealIdx + 1)
                    .map((p) => `${p.x},${p.y}`)
                    .join(' ')}
                />
                <polyline
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  strokeDasharray="4 3"
                  strokeLinejoin="round"
                  points={chart.points
                    .slice(chart.lastRealIdx)
                    .map((p) => `${p.x},${p.y}`)
                    .join(' ')}
                />
                {chart.points.map((p, i) => (
                  <circle
                    key={i}
                    cx={p.x}
                    cy={p.y}
                    r={2.5}
                    fill="var(--accent)"
                    fillOpacity={p.forecast ? 0.4 : 1}
                  />
                ))}
              </svg>
              {/* Étiquettes de mois */}
              <div className="mt-1 flex">
                {projMonths.map((m, i) => (
                  <div
                    key={m.month}
                    className={`flex-1 text-center text-[10px] text-[var(--muted)] ${m.is_forecast ? 'italic' : ''}`}
                  >
                    {MONTH_LABELS[i]}
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t border-[var(--border)] pt-3 text-sm">
                <span className="text-[var(--muted)]">Fin d&apos;année (prév.)</span>
                <span className="tabular font-medium">
                  {eur(projMonths[projMonths.length - 1]?.cumulative_cash_eur)}
                </span>
              </div>
            </>
          ) : (
            <Empty>Aucune projection disponible.</Empty>
          )}
        </Card>
      </div>

      {docsOpen && <BalanceDocsModal onClose={() => setDocsOpen(false)} />}
    </div>
  );
}
