'use client';

import { Card } from '@/components/ui';
import { eur, MONTH_LABELS } from '@/lib/format';

type Month = { month: string; balance_eur: string | number; is_forecast: boolean };

export type BalanceData = {
  year: number;
  months: Month[];
  current_balance_eur: string | number;
  projected_year_end_eur: string | number;
};

const num = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : 0;
};

const W = 400;
const H = 150;
const PAD = 14;

export function BalanceChart({ data }: { data: BalanceData }) {
  const vals = data.months.map((m) => num(m.balance_eur));
  const dMin = Math.min(0, ...vals);
  const dMax = Math.max(0, ...vals);
  const span = dMax - dMin || 1;
  const yFor = (v: number) => H - PAD - ((v - dMin) / span) * (H - 2 * PAD);
  const step = data.months.length > 1 ? W / (data.months.length - 1) : W;
  const pts = data.months.map((m, i) => ({ x: i * step, y: yFor(num(m.balance_eur)), fc: m.is_forecast }));
  const lastReal = data.months.reduce((acc, m, i) => (m.is_forecast ? acc : i), 0);
  const zeroY = yFor(0);

  const realPts = pts.slice(0, lastReal + 1);
  const fcPts = pts.slice(lastReal);
  const areaPath =
    realPts.length > 0
      ? `M${realPts[0].x},${zeroY} ` +
        realPts.map((p) => `L${p.x},${p.y}`).join(' ') +
        ` L${realPts[realPts.length - 1].x},${zeroY} Z`
      : '';

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between">
        <div className="text-sm font-semibold">Solde de trésorerie</div>
        <span className="rounded border border-[var(--border)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--muted)]">
          Tous les comptes ▾
        </span>
      </div>
      <div className="tabular text-2xl font-bold">{eur(data.current_balance_eur)}</div>
      <div className="mb-1 text-[11px] text-[var(--muted)]">
        solde actuel · projeté fin {data.year} : <b className="tabular">{eur(data.projected_year_end_eur)}</b>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" role="img" aria-label="Trajectoire du solde de trésorerie">
        <line x1={0} x2={W} y1={zeroY} y2={zeroY} stroke="var(--border)" />
        <defs>
          <linearGradient id="balFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2563eb" stopOpacity="0.18" />
            <stop offset="1" stopColor="#2563eb" stopOpacity="0" />
          </linearGradient>
        </defs>
        {areaPath && <path d={areaPath} fill="url(#balFill)" />}
        <polyline points={realPts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        <polyline points={fcPts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeDasharray="4 3" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="var(--accent)" fillOpacity={p.fc ? 0.4 : 1}>
            <title>{`${MONTH_LABELS[i]} : ${eur(data.months[i].balance_eur)}${p.fc ? ' (prévision)' : ''}`}</title>
          </circle>
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--muted)]">
        <span>{MONTH_LABELS[0]}</span>
        <span>{MONTH_LABELS[Math.floor(data.months.length / 2)]}</span>
        <span className="italic">{MONTH_LABELS[data.months.length - 1]} (prév.)</span>
      </div>
    </Card>
  );
}
