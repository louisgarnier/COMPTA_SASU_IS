'use client';

import { Fragment, useState } from 'react';
import { balanceDocsAPI, type MonthlyReconView, type ReconStatus } from '@/api/client';
import { Badge } from '@/components/ui';
import { eur, money } from '@/lib/format';

export const MOIS = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'];

export const badgeFor = (s: ReconStatus) =>
  s === 'ok' ? <Badge tone="pos">✓ ok</Badge>
  : s === 'warn' ? <Badge tone="warn">⚠ écart</Badge>
  : s === 'partial' ? <Badge tone="info">partiel</Badge>
  : s === 'empty' ? <Badge tone="neutral">—</Badge>
  : <Badge tone="neutral">manquant</Badge>;

/**
 * Tableau 12 mois du rapprochement officiel — présentationnel, aucun fetch.
 * Partagé entre la carte Banques (`selectable` : cases à cocher pour l'envoi
 * groupé) et l'onglet lecture seule du dashboard (sans sélection).
 * Le dépliage du détail par compte est un état interne : les deux vues le veulent.
 */
export function MonthlyReconcileTable({
  view,
  selectable = false,
  selected,
  onToggleMonth,
  onToggleAll,
  allSelected = false,
  hasSelectableMonths = false,
}: {
  view: MonthlyReconView;
  selectable?: boolean;
  selected?: Set<number>;
  onToggleMonth?: (m: number) => void;
  onToggleAll?: () => void;
  allSelected?: boolean;
  hasSelectableMonths?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const cols = selectable ? 6 : 5;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            {selectable && (
              <th className="w-8 py-2 pr-2 font-medium">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  disabled={!hasSelectableMonths}
                  aria-label="Tout sélectionner"
                />
              </th>
            )}
            <th className="py-2 pr-4 font-medium">Fin de mois</th>
            <th className="py-2 pr-4 text-right font-medium">Solde officiel (€)</th>
            <th className="py-2 pr-4 text-right font-medium">Écart</th>
            <th className="py-2 pr-4 font-medium">Statut</th>
            <th className="py-2 font-medium">Relevés</th>
          </tr>
        </thead>
        <tbody>
          {view.months.map((m) => (
            <Fragment key={m.month}>
              <tr
                className={`cursor-pointer border-b border-[var(--border)] last:border-0 ${
                  selected?.has(m.month) ? 'bg-blue-50' : 'hover:bg-black/[0.02]'
                }`}
                onClick={() => setOpen(open === m.month ? null : m.month)}
              >
                {selectable && (
                  <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                    {m.docs.length > 0 && (
                      <input
                        type="checkbox"
                        checked={selected?.has(m.month) ?? false}
                        onChange={() => onToggleMonth?.(m.month)}
                        aria-label={`Sélectionner ${MOIS[m.month - 1]} ${view.year}`}
                      />
                    )}
                  </td>
                )}
                <td className="py-2 pr-4">{MOIS[m.month - 1]} {view.year}</td>
                <td className="tabular py-2 pr-4 text-right">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_official)}
                </td>
                <td className="tabular py-2 pr-4 text-right">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_diff)}
                </td>
                <td className="py-2 pr-4">{badgeFor(m.status)}</td>
                <td className="py-2" onClick={(e) => e.stopPropagation()}>
                  {m.docs.length > 0 ? (
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                      {m.docs.map((d, i) => (
                        <Fragment key={d.id}>
                          {i > 0 && <span className="text-[var(--muted)]">·</span>}
                          <a
                            href={balanceDocsAPI.downloadUrl(d.id)}
                            title={d.filename}
                            className="text-[var(--accent)] hover:underline"
                          >
                            ⬇ {d.name}
                          </a>
                        </Fragment>
                      ))}
                    </span>
                  ) : (
                    <span className="text-[var(--muted)]">—</span>
                  )}
                </td>
              </tr>
              {open === m.month && m.per_account.length > 0 && (
                <tr className="border-b border-[var(--border)] bg-black/[0.02] last:border-0">
                  <td colSpan={cols} className="px-3 pb-3">
                    <table className="w-full text-xs">
                      <tbody>
                        {m.per_account.map((a) => (
                          <tr key={a.account_uid} className="border-t border-[var(--border)]">
                            <td className="py-1 pr-2">{a.currency}</td>
                            <td className="tabular py-1 pr-2 text-right">
                              {a.official == null ? '—' : money(a.official, a.currency)}
                            </td>
                            <td className="tabular py-1 pr-2 text-right">{money(a.reconstructed, a.currency)}</td>
                            <td className="tabular py-1 pr-2 text-right">
                              {a.diff == null ? '—' : money(a.diff, a.currency)}
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
  );
}
