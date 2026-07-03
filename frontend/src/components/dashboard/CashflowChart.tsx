'use client';

import { Card } from '@/components/ui';
import { MONTH_LABELS } from '@/lib/format';

const CCY: Record<string, string> = {
  USD: '#2563eb',
  CAD: '#f59e0b',
  EUR: '#16a34a',
  GBP: '#8b5cf6',
};
const CCY_ORDER = ['USD', 'CAD', 'EUR', 'GBP'];
const NEG = '#dc2626';
const HATCH =
  'repeating-linear-gradient(45deg, rgba(255,255,255,.5) 0 3px, transparent 3px 6px)';

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

// Montant compact pour label dans une barre (8704 → "8,7k").
const kEur = (v: number): string => {
  const n = Math.abs(v);
  if (!n) return '';
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace('.', ',') + 'k';
  return String(Math.round(n));
};

const H = 150;

function Seg({ h, bg, hatch, fc, label }: { h: number; bg: string; hatch?: boolean; fc?: boolean; label: string }) {
  return (
    <div
      className="flex w-full items-center justify-center overflow-hidden"
      style={{ height: `${h}px`, background: bg, backgroundImage: hatch ? HATCH : undefined, opacity: fc ? 0.42 : 1 }}
    >
      {h >= 13 && label && (
        <span className="tabular text-[8px] font-semibold leading-none text-white">{label}</span>
      )}
    </div>
  );
}

export function CashflowChart({ data }: { data: CashflowData }) {
  const inTotal = (m: Month) => CCY_ORDER.reduce((a, c) => a + num(m.incoming_by_ccy[c]), 0);
  const outTotal = (m: Month) => num(m.outgoing_eur);
  const max = Math.max(1, ...data.months.map((m) => Math.max(inTotal(m), outTotal(m))));
  const usedCcy = CCY_ORDER.filter((c) => data.months.some((m) => num(m.incoming_by_ccy[c]) > 0));

  // Split réel (mois passés) vs prévision (mois futurs) — calculé côté front.
  const sum = (pick: (m: Month) => number, fc: boolean) =>
    data.months.filter((m) => !!m.is_forecast === fc).reduce((a, m) => a + pick(m), 0);
  const inReal = sum((m) => num(m.incoming_eur), false);
  const inFc = sum((m) => num(m.incoming_eur), true);
  const outReal = sum((m) => num(m.outgoing_eur), false);
  const outFc = sum((m) => num(m.outgoing_eur), true);
  const netReal = inReal - outReal;
  const netFc = inFc - outFc;
  const c0 = (v: number) => (v ? Math.round(v).toLocaleString('fr-FR') : '—');
  const signed = (v: number) => (v >= 0 ? '+' : '−') + Math.round(Math.abs(v)).toLocaleString('fr-FR');

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
          <span>
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: NEG, backgroundImage: HATCH }} />
            Sorties
          </span>
          <span>· pâle = prévision</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-[1fr_248px] md:items-center">
        <div className="flex items-end gap-2">
          {data.months.map((m, i) => {
            const net = num(m.incoming_eur) - num(m.outgoing_eur);
            return (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex w-full items-end justify-center gap-[3px]" style={{ height: H }}>
                  {/* Entrées : empilées par devise */}
                  <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t">
                    {CCY_ORDER.filter((c) => num(m.incoming_by_ccy[c]) > 0).map((c) => (
                      <Seg key={c} h={(num(m.incoming_by_ccy[c]) / max) * H} bg={CCY[c]} fc={m.is_forecast} label={kEur(num(m.incoming_by_ccy[c]))} />
                    ))}
                  </div>
                  {/* Sorties : bloc rouge hachuré */}
                  <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t">
                    {num(m.outgoing_eur) > 0 && (
                      <Seg h={(num(m.outgoing_eur) / max) * H} bg={NEG} hatch fc={m.is_forecast} label={kEur(num(m.outgoing_eur))} />
                    )}
                  </div>
                </div>
                <div className={`text-[10px] leading-tight text-[var(--muted)] ${m.is_forecast ? 'italic' : ''}`}>
                  {MONTH_LABELS[i]}
                </div>
                <div className={`tabular text-[9px] font-semibold leading-none ${net >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
                  {net >= 0 ? '+' : '−'}
                  {kEur(net) || '0'}
                </div>
              </div>
            );
          })}
        </div>

        <table className="w-full text-sm tabular">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
              <th className="pb-1.5 text-left font-semibold">EUR</th>
              <th className="pb-1.5 pl-2 text-right font-semibold">Réel</th>
              <th className="pb-1.5 pl-2 text-right font-semibold">Prévision</th>
              <th className="pb-1.5 pl-2 text-right font-semibold text-[var(--text)]">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-[var(--border)]">
              <td className="py-1.5 text-left text-[var(--muted)]">Entrées</td>
              <td className="py-1.5 pl-2 text-right font-semibold text-[var(--pos)]">{c0(inReal)}</td>
              <td className="py-1.5 pl-2 text-right text-[var(--muted)]">{c0(inFc)}</td>
              <td className="py-1.5 pl-2 text-right font-bold text-[var(--pos)]">{c0(inReal + inFc)}</td>
            </tr>
            <tr className="border-t border-[var(--border)]">
              <td className="py-1.5 text-left text-[var(--muted)]">Sorties</td>
              <td className="py-1.5 pl-2 text-right font-semibold text-[var(--neg)]">{c0(outReal)}</td>
              <td className="py-1.5 pl-2 text-right text-[var(--muted)]">{c0(outFc)}</td>
              <td className="py-1.5 pl-2 text-right font-bold text-[var(--neg)]">{c0(outReal + outFc)}</td>
            </tr>
            <tr className="border-t-2 border-[var(--border)]">
              <td className="py-1.5 text-left font-semibold">Net</td>
              <td className={`py-1.5 pl-2 text-right font-semibold ${netReal >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>{signed(netReal)}</td>
              <td className={`py-1.5 pl-2 text-right ${netFc >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>{signed(netFc)}</td>
              <td className={`py-1.5 pl-2 text-right font-bold ${netReal + netFc >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>{signed(netReal + netFc)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  );
}
