'use client';

import { useEffect, useState } from 'react';
import { investmentsAPI } from '@/api/client';
import { Card } from '@/components/ui';
import { eur, MONTH_LABELS } from '@/lib/format';

type Month = { month: string; balance_eur: string | number; is_forecast: boolean };

export type BalanceData = {
  year: number;
  months: Month[];
  current_balance_eur: string | number;
  projected_year_end_eur: string | number;
};

type Investment = {
  current_value_eur: string | number;
  expected_month?: string | null;
  closed_date?: string | null;
};

const num = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : 0;
};

const W = 400;
const H = 150;
const PAD = 14;

export function BalanceChart({ data, scope }: { data: BalanceData; scope?: string }) {
  // Toggle « + placements » : superpose la trajectoire banque + placements
  // détenus. Pas d'historique de cours → chaque placement vaut sa dernière
  // valeur connue sur toute la courbe, et en sort quand son remboursement
  // rejoint la courbe banque (échéance attendue en scope prévisionnel, ou
  // clôture réelle rapprochée).
  const [withPlacements, setWithPlacements] = useState(false);
  const [placements, setPlacements] = useState<Investment[]>([]);
  useEffect(() => {
    investmentsAPI
      .list()
      .then((rows) => setPlacements(rows as Investment[]))
      .catch(() => setPlacements([]));
  }, []);

  // Valeur des placements encore détenus au mois m ('YYYY-MM').
  const heldAt = (monthKey: string) =>
    placements.reduce((sum, p) => {
      if (p.closed_date && p.closed_date.slice(0, 7) <= monthKey) return sum;
      if (scope === 'forecast' && p.expected_month && p.expected_month <= monthKey) return sum;
      return sum + num(p.current_value_eur);
    }, 0);

  const placTotal = placements.reduce((s, p) => s + num(p.current_value_eur), 0);

  const vals = data.months.map((m) => num(m.balance_eur));
  const valsPlac = data.months.map((m) => num(m.balance_eur) + heldAt(m.month));
  const showPlac = withPlacements && placTotal > 0;
  const dMin = Math.min(0, ...vals, ...(showPlac ? valsPlac : []));
  const dMax = Math.max(0, ...vals, ...(showPlac ? valsPlac : []));
  const span = dMax - dMin || 1;
  const yFor = (v: number) => H - PAD - ((v - dMin) / span) * (H - 2 * PAD);
  const step = data.months.length > 1 ? W / (data.months.length - 1) : W;
  const pts = data.months.map((m, i) => ({ x: i * step, y: yFor(num(m.balance_eur)), fc: m.is_forecast }));
  const placPts = data.months.map((m, i) => ({ x: i * step, y: yFor(valsPlac[i]) }));
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

  const projPlac =
    data.months.length > 0 ? valsPlac[data.months.length - 1] : num(data.projected_year_end_eur);

  return (
    <Card>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold">Trésorerie (hors placements)</div>
        {placTotal > 0 && (
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-[var(--muted)]">
            <input
              type="checkbox"
              checked={withPlacements}
              onChange={(e) => setWithPlacements(e.target.checked)}
            />
            + placements <span className="tabular">({eur(placTotal)})</span>
          </label>
        )}
      </div>
      <div className="tabular text-2xl font-bold">{eur(data.current_balance_eur)}</div>
      <div className="mb-1 text-[11px] text-[var(--muted)]">
        solde bancaire actuel · projeté fin {data.year} : <b className="tabular">{eur(data.projected_year_end_eur)}</b>
        {showPlac && (
          <span className="text-[var(--accent)]">
            {' '}· avec placements : <b className="tabular">{eur(projPlac)}</b>
          </span>
        )}
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
        {showPlac && (
          <polyline
            points={placPts.map((p) => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke="#7c3aed"
            strokeWidth={2}
            strokeDasharray="6 3"
            strokeLinejoin="round"
          >
            <title>Banque + placements détenus (dernière valeur connue)</title>
          </polyline>
        )}
        <polyline points={realPts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        <polyline points={fcPts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeDasharray="4 3" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="var(--accent)" fillOpacity={p.fc ? 0.4 : 1}>
            <title>{`${MONTH_LABELS[i]} : ${eur(data.months[i].balance_eur)}${p.fc ? ' (prévision)' : ''}${
              showPlac ? ` · avec placements : ${eur(valsPlac[i])}` : ''
            }`}</title>
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
