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
  year?: number;
  is_regime?: 'IR' | 'IS';
  revenue_eur: string | number;
  charges_eur: string | number;
  result_eur: string | number;
  is_estimate_eur: string | number;
  net_result_eur: string | number;
  retained_earnings_eur: string | number;
  distributable_eur: string | number;
  distributed_this_year_eur?: string | number;
  remaining_distributable_eur?: string | number;
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
      <div className="mb-1 text-sm font-semibold">P&amp;L (réalisé à date)</div>

      <div className="my-3 flex flex-wrap items-center gap-x-2.5 gap-y-2">
        <Cell label="Revenus" value={eur(data.revenue_eur)} />
        <Op sign="−" />
        <Cell label="Charges" value={eur(data.charges_eur)} />
        <Op sign="=" />
        <Cell label="Résultat" value={eur(data.result_eur)} tone="pos" />
        <Op sign="−" />
        <Cell label={data.is_regime === 'IR' ? 'IS — régime IR' : 'IS (réalisé à date)'} value={eur(data.is_estimate_eur)} />
        <Op sign="=" />
        <Cell label="Résultat net" value={eur(data.net_result_eur)} tone="pos" />
      </div>

      {(() => {
        // Maquette validée 2026-07-09 : RAN affiché NET des versements de
        // l'exercice (plancher 0, jamais négatif) ; l'excédent apparaît comme
        // « Acomptes sur l'exercice » ; le chiffre final = restant réel.
        // Tout est dérivé des transactions catégorisées « distribution ».
        const num = (v: string | number | undefined) => {
          const n = typeof v === 'string' ? parseFloat(v) : v ?? 0;
          return Number.isFinite(n) ? n : 0;
        };
        const ranBrut = num(data.retained_earnings_eur);
        const verse = num(data.distributed_this_year_eur);
        const ranNet = Math.max(0, ranBrut - verse);
        const acomptes = Math.max(0, verse - ranBrut);
        const restant = num(data.remaining_distributable_eur ?? data.distributable_eur);
        return (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5">
            <div className="mb-1.5 text-[11px] font-semibold text-[var(--muted)]">
              Résultat distribuable <span className="font-normal">(réserves + exercice)</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
              <Cell label="Résultat net" value={eur(data.net_result_eur)} tone="pos" />
              <Op sign="+" />
              <Cell
                label={verse > 0 ? 'Report à nouveau (net des versements)' : 'Report à nouveau (cumul auto)'}
                value={eur(ranNet)}
              />
              {acomptes > 0 && (
                <>
                  <Op sign="−" />
                  <Cell label="Acomptes sur l'exercice" value={eur(acomptes)} />
                </>
              )}
              <Op sign="=" />
              <Cell
                label="Distribuable (restant)"
                value={eur(restant)}
                tone={restant >= 0 ? 'pos' : undefined}
              />
            </div>
            {verse > 0 && (
              <div className="mt-1.5 text-[11px] text-[var(--muted)]">
                Report à nouveau initial : <b>{eur(ranBrut)}</b> − versé cet exercice :{' '}
                <b>{eur(verse)}</b>
                {acomptes > 0 && (
                  <>
                    {' '}
                    (dont <b>{eur(acomptes)}</b> en acompte sur le résultat {data.year ?? ''})
                  </>
                )}
                {acomptes === 0 && ranNet === 0 && <> → soldé.</>}
              </div>
            )}
            {restant < 0 && (
              <div className="mt-1.5 text-[11px] font-semibold text-red-600">
                ⚠ Distributions supérieures au distribuable — sur-distribution à régulariser.
              </div>
            )}
          </div>
        );
      })()}

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
