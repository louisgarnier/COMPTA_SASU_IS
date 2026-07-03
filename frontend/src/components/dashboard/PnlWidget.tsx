'use client';

import { Card } from '@/components/ui';
import { eur, money } from '@/lib/format';

const CCY: Record<string, string> = {
  EUR: '#16a34a',
  USD: '#2563eb',
  CAD: '#f59e0b',
  GBP: '#8b5cf6',
};

type Ccy = {
  currency: string;
  revenue_native: string | number;
  revenue_eur: string | number;
  charges_eur: string | number;
};

export type PnlSummary = {
  revenue_eur: string | number;
  charges_eur: string | number;
  result_eur: string | number;
  is_estimate_eur: string | number;
  net_result_eur: string | number;
  retained_earnings_eur: string | number;
  distributable_eur: string | number;
  by_currency: Ccy[];
};

function Op({ sign }: { sign: '−' | '=' | '+' }) {
  const bg = sign === '−' ? 'var(--neg)' : sign === '+' ? 'var(--pos)' : '#6b7280';
  return (
    <span
      className="flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold text-white"
      style={{ background: bg }}
      aria-hidden
    >
      {sign}
    </span>
  );
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: 'pos' }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className={`tabular text-lg font-bold ${tone === 'pos' ? 'text-[var(--pos)]' : ''}`}>
        {value}
      </div>
    </div>
  );
}

export function PnlWidget({ data }: { data: PnlSummary }) {
  return (
    <Card>
      <div className="mb-1 text-sm font-semibold">Profit &amp; Loss (live)</div>

      <div className="my-3 flex flex-wrap items-center gap-x-2.5 gap-y-2">
        <Cell label="Revenus" value={eur(data.revenue_eur)} />
        <Op sign="−" />
        <Cell label="Charges" value={eur(data.charges_eur)} />
        <Op sign="=" />
        <Cell label="Résultat" value={eur(data.result_eur)} tone="pos" />
        <Op sign="−" />
        <Cell label="IS estimé" value={eur(data.is_estimate_eur)} />
        <Op sign="=" />
        <Cell label="Résultat net" value={eur(data.net_result_eur)} tone="pos" />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5">
        <div className="mb-1.5 text-[11px] font-semibold text-[var(--muted)]">
          Résultat distribuable <span className="font-normal">(réserves + exercice)</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
          <Cell label="Résultat net" value={eur(data.net_result_eur)} tone="pos" />
          <Op sign="+" />
          <Cell label="Report à nouveau" value={eur(data.retained_earnings_eur)} />
          <Op sign="=" />
          <Cell label="Distribuable" value={eur(data.distributable_eur)} tone="pos" />
        </div>
      </div>

      <table className="mt-3 w-full text-sm tabular">
        <thead>
          <tr className="text-right text-[10px] uppercase text-[var(--muted)]">
            <th className="py-1.5 pr-2 text-left font-semibold">Devise</th>
            <th className="px-2 py-1.5 font-semibold">Revenus (natif)</th>
            <th className="px-2 py-1.5 font-semibold">= EUR</th>
            <th className="px-2 py-1.5 font-semibold">Charges (EUR)</th>
          </tr>
        </thead>
        <tbody>
          {data.by_currency.map((c) => (
            <tr key={c.currency} className="border-t border-[var(--border)]">
              <td className="py-1.5 pr-2">
                <span
                  className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]"
                  style={{ background: CCY[c.currency] ?? '#6b7280' }}
                />
                {c.currency}
              </td>
              <td className="px-2 py-1.5 text-right">{money(c.revenue_native, c.currency)}</td>
              <td className="px-2 py-1.5 text-right">{eur(c.revenue_eur)}</td>
              <td className="px-2 py-1.5 text-right text-[var(--neg)]">
                {Number(c.charges_eur) ? `−${eur(c.charges_eur)}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
