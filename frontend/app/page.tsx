'use client';

import { useEffect, useState } from 'react';
import { treasuryAPI, investmentsAPI, forecastAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { eur, money, MONTH_LABELS } from '@/lib/format';

type Account = {
  account_uid: string;
  name: string;
  provider: string;
  currency: string;
  balance: string | number;
};

type Treasury = {
  accounts: Account[];
  bank_total_eur: string | number;
  investments_total_eur: string | number;
  total_eur: string | number;
};

type PnlMonth = {
  month: string;
  revenue_eur: string | number;
  charges_eur: string | number;
  result_eur: string | number;
};

type Pnl = {
  year: number;
  months: PnlMonth[];
  totals: { revenue_eur: string | number; charges_eur: string | number; result_eur: string | number };
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
  net_eur: string | number;
  cumulative_cash_eur: string | number;
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

  useEffect(() => {
    Promise.all([
      treasuryAPI.get(),
      treasuryAPI.pnl(2026),
      investmentsAPI.summary(),
      forecastAPI.get(2026),
    ])
      .then(([t, p, i, f]) => {
        setTreasury(t);
        setPnl(p);
        setInvest(i);
        setForecast(f);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

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

  // Échelle du graphe P&L : max valeur absolue sur revenus / charges
  const pnlMax = Math.max(
    1,
    ...(pnl?.months ?? []).flatMap((m) => [
      Math.abs(num(m.revenue_eur)),
      Math.abs(num(m.charges_eur)),
    ]),
  );

  const projMonths = forecast?.projection.months ?? [];
  const cashMax = Math.max(
    1,
    ...projMonths.map((m) => Math.abs(num(m.cumulative_cash_eur))),
  );

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

      {/* P&L mensuel — graphe barres CSS */}
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <div className="text-sm font-semibold">P&amp;L mensuel 2026</div>
          <div className="flex items-center gap-4 text-xs text-[var(--muted)]">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm bg-[var(--pos)]" /> Revenus
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm bg-[var(--neg)]" /> Charges
            </span>
          </div>
        </div>
        <div className="flex items-end gap-2">
          {(pnl?.months ?? []).map((m, i) => {
            const rev = Math.abs(num(m.revenue_eur));
            const chg = Math.abs(num(m.charges_eur));
            return (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex w-full items-end justify-center gap-0.5" style={{ height: 175 }}>
                  <div
                    className="w-1/2 rounded-t bg-[var(--pos)]"
                    style={{ height: `${(rev / pnlMax) * 175}px` }}
                    title={`Revenus ${eur(m.revenue_eur)}`}
                  />
                  <div
                    className="w-1/2 rounded-t bg-[var(--neg)]"
                    style={{ height: `${(chg / pnlMax) * 175}px` }}
                    title={`Charges ${eur(m.charges_eur)}`}
                  />
                </div>
                <div className="text-[10px] text-[var(--muted)]">{MONTH_LABELS[i]}</div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex justify-between border-t border-[var(--border)] pt-3 text-sm">
          <span className="text-[var(--muted)]">
            Revenus <span className="tabular font-medium text-[var(--text)]">{eur(pnl?.totals.revenue_eur)}</span>
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
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Comptes */}
        <Card>
          <div className="mb-4 text-sm font-semibold">Comptes</div>
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
            </div>
          ) : (
            <Empty>Aucun compte connecté.</Empty>
          )}
        </Card>

        {/* Prévision tréso */}
        <Card>
          <div className="mb-4 text-sm font-semibold">Prévision tréso (cash cumulé)</div>
          {projMonths.length > 0 ? (
            <>
              <div className="flex items-end gap-1.5">
                {projMonths.map((m, i) => {
                  const c = num(m.cumulative_cash_eur);
                  return (
                    <div key={m.month} className="flex flex-1 flex-col items-center justify-end gap-1">
                      <div className="flex w-full items-end" style={{ height: 110 }}>
                        <div
                          className={`w-full rounded-t ${c >= 0 ? 'bg-[var(--accent)]' : 'bg-[var(--neg)]'}`}
                          style={{ height: `${(Math.abs(c) / cashMax) * 110}px` }}
                          title={`${MONTH_LABELS[i]} : ${eur(c)}`}
                        />
                      </div>
                      <div className="text-[10px] text-[var(--muted)]">{MONTH_LABELS[i]}</div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex justify-between border-t border-[var(--border)] pt-3 text-sm">
                <span className="text-[var(--muted)]">Fin d'année</span>
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
    </div>
  );
}
