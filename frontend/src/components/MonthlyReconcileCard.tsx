'use client';

import { Fragment, useEffect, useState } from 'react';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { eur } from '@/lib/format';

const MOIS = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'];

const badgeFor = (s: string) =>
  s === 'ok' ? <Badge tone="pos">✓ ok</Badge>
  : s === 'warn' ? <Badge tone="warn">⚠ écart</Badge>
  : <Badge tone="neutral">manquant</Badge>;

export function MonthlyReconcileCard({ year }: { year: number }) {
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    monthlyBalancesAPI.reconciliation(year).then(setView).catch(() => setView(null));
  }, [year]);

  if (!view) return <Card><p className="text-sm text-[var(--muted)]">Chargement…</p></Card>;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Rapprochement mensuel officiel</h3>
        <span className="text-sm text-[var(--muted)]">
          Couverture <strong>{view.coverage}</strong> mois
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="py-2 pr-4 font-medium">Fin de mois</th>
              <th className="py-2 pr-4 text-right font-medium">Solde officiel (€)</th>
              <th className="py-2 pr-4 text-right font-medium">Écart</th>
              <th className="py-2 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody>
            {view.months.map((m) => (
              <Fragment key={m.month}>
                <tr
                  className="cursor-pointer border-b border-[var(--border)] last:border-0 hover:bg-black/[0.02]"
                  onClick={() => setOpen(open === m.month ? null : m.month)}
                >
                  <td className="py-2 pr-4">{MOIS[m.month - 1]} {view.year}</td>
                  <td className="tabular py-2 pr-4 text-right">
                    {m.status === 'missing' ? '—' : eur(m.total_eur_official)}
                  </td>
                  <td className="tabular py-2 pr-4 text-right">
                    {m.status === 'missing' ? '—' : eur(m.total_eur_diff)}
                  </td>
                  <td className="py-2">{badgeFor(m.status)}</td>
                </tr>
                {open === m.month && m.per_account.length > 0 && (
                  <tr className="border-b border-[var(--border)] bg-black/[0.02] last:border-0">
                    <td colSpan={4} className="px-3 pb-3">
                      <table className="w-full text-xs">
                        <tbody>
                          {m.per_account.map((a) => (
                            <tr key={a.account_uid} className="border-t border-[var(--border)]">
                              <td className="py-1 pr-2">{a.currency}</td>
                              <td className="tabular py-1 pr-2 text-right">
                                {a.official == null ? '—' : eur(a.official)}
                              </td>
                              <td className="tabular py-1 pr-2 text-right">{eur(a.reconstructed)}</td>
                              <td className="tabular py-1 pr-2 text-right">
                                {a.diff == null ? '—' : eur(a.diff)}
                              </td>
                              <td className="py-1">{badgeFor(a.status)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
