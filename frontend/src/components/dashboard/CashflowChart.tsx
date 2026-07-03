'use client';

import { Card } from '@/components/ui';
import { eur, MONTH_LABELS } from '@/lib/format';

const CCY: Record<string, string> = {
  USD: '#2563eb',
  CAD: '#f59e0b',
  EUR: '#16a34a',
  GBP: '#8b5cf6',
};
const CCY_ORDER = ['USD', 'CAD', 'EUR', 'GBP'];
const HATCH =
  'repeating-linear-gradient(45deg, rgba(255,255,255,.55) 0 2px, transparent 2px 4px)';

type Month = {
  month: string;
  incoming_by_ccy: Record<string, string | number>;
  outgoing_by_ccy: Record<string, string | number>;
  incoming_eur: string | number;
  outgoing_eur: string | number;
  is_forecast: boolean;
};

export type CashflowData = {
  year: number;
  months: Month[];
  totals: { incoming_eur: string | number; outgoing_eur: string | number; net_eur: string | number };
};

const num = (v: string | number | undefined) => {
  const n = typeof v === 'string' ? parseFloat(v) : v ?? 0;
  return Number.isFinite(n) ? n : 0;
};

function Bar({ map, max, hatch, fc }: { map: Record<string, string | number>; max: number; hatch?: boolean; fc?: boolean }) {
  const H = 150;
  return (
    <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t">
      {CCY_ORDER.filter((c) => num(map[c]) > 0).map((c) => (
        <div
          key={c}
          style={{
            height: `${(num(map[c]) / max) * H}px`,
            background: CCY[c],
            backgroundImage: hatch ? HATCH : undefined,
            opacity: fc ? 0.42 : 1,
          }}
        />
      ))}
    </div>
  );
}

export function CashflowChart({ data }: { data: CashflowData }) {
  const sum = (m: Record<string, string | number>) =>
    Object.values(m).reduce((a: number, v) => a + num(v), 0);
  const max = Math.max(
    1,
    ...data.months.flatMap((m) => [sum(m.incoming_by_ccy), sum(m.outgoing_by_ccy)]),
  );
  const usedCcy = CCY_ORDER.filter((c) =>
    data.months.some((m) => num(m.incoming_by_ccy[c]) > 0 || num(m.outgoing_by_ccy[c]) > 0),
  );
  return (
    <Card>
      <div className="mb-1 flex flex-wrap items-start justify-between gap-2">
        <div className="text-sm font-semibold">Cashflow — entrées / sorties par mois</div>
        <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-[var(--muted)]">
          {usedCcy.map((c) => (
            <span key={c}>
              <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: CCY[c] }} />
              {c}
            </span>
          ))}
          <span>· plein = <b>entrées</b> · hachuré = <b>sorties</b> · pâle = prévision</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-[1fr_190px] md:items-center">
        <div className="flex items-end gap-2" style={{ height: 170 }}>
          {data.months.map((m, i) => (
            <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full items-end justify-center gap-[3px]" style={{ height: 150 }}>
                <Bar map={m.incoming_by_ccy} max={max} fc={m.is_forecast} />
                <Bar map={m.outgoing_by_ccy} max={max} hatch fc={m.is_forecast} />
              </div>
              <div className={`text-[10px] text-[var(--muted)] ${m.is_forecast ? 'italic' : ''}`}>
                {MONTH_LABELS[i]}
              </div>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Total entrées (EUR)</div>
            <div className="tabular text-xl font-bold text-[var(--pos)]">{eur(data.totals.incoming_eur)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Total sorties (EUR)</div>
            <div className="tabular text-xl font-bold text-[var(--neg)]">{eur(data.totals.outgoing_eur)}</div>
          </div>
          <div className="border-t border-[var(--border)] pt-2.5">
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Solde net (EUR)</div>
            <div
              className={`tabular text-xl font-bold ${num(data.totals.net_eur) >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}
            >
              {num(data.totals.net_eur) >= 0 ? '+' : ''}
              {eur(data.totals.net_eur)}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
