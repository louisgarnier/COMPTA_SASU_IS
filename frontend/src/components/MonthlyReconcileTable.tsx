'use client';

import { Fragment, useEffect, useState } from 'react';
import { balanceDocsAPI, monthlyBalancesAPI, type MonthlyReconView, type ReconStatus } from '@/api/client';
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
 * Tableau 12 mois du rapprochement officiel — présentationnel côté fetch (le
 * `view` est fourni par le parent), mais propriétaire de son état de
 * sélection quand `selectable` est vrai : cases à cocher, barre d'action
 * (téléchargement groupé + stub mail) et dépliage du détail par compte.
 * Partagé entre la carte Banques et l'onglet lecture seule du dashboard —
 * les deux veulent la sélection, seule la carte Banques ajoute par-dessus la
 * dropzone de dépôt et la proposition de soldes éditable.
 */
export function MonthlyReconcileTable({
  view,
  selectable = false,
}: {
  view: MonthlyReconView;
  selectable?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const cols = selectable ? 6 : 5;

  // la sélection ne doit pas survivre à un changement d'exercice affiché
  useEffect(() => {
    setSelected(new Set());
  }, [view.year]);

  // mois qui ont au moins un relevé archivé (sélectionnables)
  const monthsWithDocs = view.months.filter((m) => m.docs.length > 0);
  const allSelected = monthsWithDocs.length > 0 && monthsWithDocs.every((m) => selected.has(m.month));

  const toggleMonth = (mth: number) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(mth)) next.delete(mth);
      else next.add(mth);
      return next;
    });
  };
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(monthsWithDocs.map((m) => m.month)));

  // relevés (doc ids) des mois cochés
  const selectedDocIds = view.months
    .filter((m) => selected.has(m.month))
    .flatMap((m) => m.docs.map((d) => d.id));

  const downloadSelected = () => {
    if (selectedDocIds.length === 0) return;
    window.open(monthlyBalancesAPI.archiveUrl(selectedDocIds), '_blank');
  };
  const mailSelected = () => {
    // Envoi par mail à configurer ultérieurement (SMTP + destinataire).
    alert(
      `Envoi par mail à configurer.\n${selectedDocIds.length} relevé(s) seront joints ` +
        `(${selected.size} mois sélectionné(s)).`,
    );
  };

  return (
    <div>
      {selectable && selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2">
          <span className="text-sm font-semibold text-blue-700">
            {selected.size} mois sélectionné{selected.size > 1 ? 's' : ''}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={downloadSelected}
              disabled={selectedDocIds.length === 0}
              className="inline-flex items-center gap-1 rounded border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            >
              ⬇ Télécharger les relevés ({selectedDocIds.length})
            </button>
            <button
              type="button"
              onClick={mailSelected}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
            >
              ✉ Envoyer par mail
            </button>
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            {selectable && (
              <th className="w-8 py-2 pr-2 font-medium">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  disabled={monthsWithDocs.length === 0}
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
                  selected.has(m.month) ? 'bg-blue-50' : 'hover:bg-black/[0.02]'
                }`}
                onClick={() => setOpen(open === m.month ? null : m.month)}
              >
                {selectable && (
                  <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                    {m.docs.length > 0 && (
                      <input
                        type="checkbox"
                        checked={selected.has(m.month)}
                        onChange={() => toggleMonth(m.month)}
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
    </div>
  );
}
