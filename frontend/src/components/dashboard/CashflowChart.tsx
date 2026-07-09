'use client';

import { useState } from 'react';
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
  // Part ATTENDUE (non encaissée) — affichée pâle, exclue du « Réel ».
  incoming_expected_by_ccy?: Record<string, string | number>;
  incoming_expected_eur?: string | number;
  outgoing_forecast_eur?: string | number;
  // Parts liées à des factures d'exercices ANTÉRIEURS (vue fiscale les retire).
  incoming_prior_by_ccy?: Record<string, string | number>;
  incoming_prior_expected_by_ccy?: Record<string, string | number>;
  is_forecast: boolean;
};

export type CashflowData = {
  year: number;
  months: Month[];
  totals: { incoming_eur: string | number; outgoing_eur: string | number; net_eur: string | number };
  // Factures de l'exercice encaissées / attendues APRÈS le 31/12 (vue fiscale).
  overflow?: {
    expected_by_ccy: Record<string, string | number>;
    real_by_ccy: Record<string, string | number>;
  };
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
  // Vue caisse (« Année en cours » : tout le cash de l'année) vs vue fiscale
  // (« Année fiscale » : cash lié à l'activité de l'exercice — on retire les
  // encaissements de factures antérieures, on ajoute le débordement N+1).
  const [scope, setScope] = useState<'cash' | 'fiscal'>('cash');
  const fiscal = scope === 'fiscal';

  // Montants ajustés selon la vue.
  const adjIn = (m: Month, c: string) =>
    num(m.incoming_by_ccy[c]) -
    (fiscal
      ? num(m.incoming_prior_by_ccy?.[c]) + num(m.incoming_prior_expected_by_ccy?.[c])
      : 0);
  const adjExp = (m: Month, c: string) =>
    num(m.incoming_expected_by_ccy?.[c]) -
    (fiscal ? num(m.incoming_prior_expected_by_ccy?.[c]) : 0);

  // Débordement N+1 (vue fiscale) : factures de l'exercice payées/attendues après le 31/12.
  const ovExp = (c: string) => num(data.overflow?.expected_by_ccy?.[c]);
  const ovReal = (c: string) => num(data.overflow?.real_by_ccy?.[c]);
  const overflowTotal = CCY_ORDER.reduce((a, c) => a + ovExp(c) + ovReal(c), 0);
  const showOverflow = fiscal && overflowTotal > 0;

  const inTotal = (m: Month) => CCY_ORDER.reduce((a, c) => a + adjIn(m, c), 0);
  const outTotal = (m: Month) => num(m.outgoing_eur);
  const max = Math.max(
    1,
    ...data.months.map((m) => Math.max(inTotal(m), outTotal(m))),
    showOverflow ? overflowTotal : 0,
  );
  const usedCcy = CCY_ORDER.filter(
    (c) =>
      data.months.some((m) => adjIn(m, c) > 0) || (showOverflow && ovExp(c) + ovReal(c) > 0),
  );

  // Split réel vs prévision : « Réel » = uniquement l'argent effectivement
  // passé en banque ; l'attendu (mois courant inclus) compte en prévision (pâle).
  const sumAll = (pick: (m: Month) => number) =>
    data.months.reduce((a, m) => a + pick(m), 0);
  const inFc =
    sumAll((m) => CCY_ORDER.reduce((a, c) => a + adjExp(m, c), 0)) +
    (fiscal ? CCY_ORDER.reduce((a, c) => a + ovExp(c), 0) : 0);
  const inReal =
    sumAll((m) => inTotal(m)) -
    sumAll((m) => CCY_ORDER.reduce((a, c) => a + adjExp(m, c), 0)) +
    (fiscal ? CCY_ORDER.reduce((a, c) => a + ovReal(c), 0) : 0);
  const outFc = sumAll((m) => num(m.outgoing_forecast_eur));
  const outReal = sumAll((m) => num(m.outgoing_eur)) - outFc;
  const netReal = inReal - outReal;
  const netFc = inFc - outFc;
  const c0 = (v: number) => (v ? Math.round(v).toLocaleString('fr-FR') : '—');
  const signed = (v: number) => (v >= 0 ? '+' : '−') + Math.round(Math.abs(v)).toLocaleString('fr-FR');

  return (
    <Card>
      <div className="mb-1 flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="text-sm font-semibold">Cashflow — entrées / sorties par mois</div>
          {/* Vue caisse vs fiscale (retire les factures N-1, ajoute le débordement N+1). */}
          <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)] text-[11px]">
            <button
              onClick={() => setScope('cash')}
              className={`px-2 py-0.5 font-medium ${!fiscal ? 'bg-[var(--accent)] text-white' : 'text-[var(--muted)] hover:bg-gray-50'}`}
            >
              Année en cours
            </button>
            <button
              onClick={() => setScope('fiscal')}
              className={`border-l border-[var(--border)] px-2 py-0.5 font-medium ${fiscal ? 'bg-[var(--accent)] text-white' : 'text-[var(--muted)] hover:bg-gray-50'}`}
            >
              Année fiscale
            </button>
          </div>
        </div>
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
            const net = inTotal(m) - num(m.outgoing_eur);
            return (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex w-full items-end justify-center gap-[3px]" style={{ height: H }}>
                  {/* Entrées : empilées par devise — part ATTENDUE en pâle,
                      part réellement encaissée en couleur pleine. */}
                  <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t">
                    {CCY_ORDER.filter((c) => adjIn(m, c) > 0).map((c) => {
                      const total = adjIn(m, c);
                      const exp = Math.min(adjExp(m, c), total);
                      const real = total - exp;
                      return (
                        <div key={c} className="contents">
                          {exp > 0 && <Seg h={(exp / max) * H} bg={CCY[c]} fc label={kEur(exp)} />}
                          {real > 0 && <Seg h={(real / max) * H} bg={CCY[c]} label={kEur(real)} />}
                        </div>
                      );
                    })}
                  </div>
                  {/* Sorties : rouge hachuré — prorata prévisionnel en pâle. */}
                  <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t">
                    {(() => {
                      const total = num(m.outgoing_eur);
                      const fc = Math.min(num(m.outgoing_forecast_eur), total);
                      const real = total - fc;
                      return (
                        <>
                          {fc > 0 && <Seg h={(fc / max) * H} bg={NEG} hatch fc label={kEur(fc)} />}
                          {real > 0 && <Seg h={(real / max) * H} bg={NEG} hatch label={kEur(real)} />}
                        </>
                      );
                    })()}
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
          {/* Vue fiscale : 13e colonne = factures de l'exercice encaissées
              début N+1 (déc payée mi-février, etc.). */}
          {showOverflow && (
            <div className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full items-end justify-center gap-[3px]" style={{ height: H }}>
                <div className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t border-x border-t border-dashed border-[var(--border)]">
                  {CCY_ORDER.filter((c) => ovExp(c) + ovReal(c) > 0).map((c) => (
                    <div key={c} className="contents">
                      {ovExp(c) > 0 && <Seg h={(ovExp(c) / max) * H} bg={CCY[c]} fc label={kEur(ovExp(c))} />}
                      {ovReal(c) > 0 && <Seg h={(ovReal(c) / max) * H} bg={CCY[c]} label={kEur(ovReal(c))} />}
                    </div>
                  ))}
                </div>
              </div>
              <div className="text-[10px] italic leading-tight text-[var(--muted)]">→{data.year + 1}</div>
              <div className="tabular text-[9px] font-semibold leading-none text-[var(--pos)]">
                +{kEur(overflowTotal) || '0'}
              </div>
            </div>
          )}
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
