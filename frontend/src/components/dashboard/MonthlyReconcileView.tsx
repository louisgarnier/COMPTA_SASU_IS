'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { MonthlyReconcileTable } from '@/components/MonthlyReconcileTable';

/**
 * Onglet « Rapprochement mensuel » du dashboard — lecture seule côté écriture
 * (maquette variante A, validée 2026-07-17) : le dépôt de relevé et la
 * proposition de soldes éditable restent exclusivement sur la page Banques,
 * ici on ne modifie jamais la base. La sélection multi-mois et le
 * téléchargement groupé, eux, sont partagés via `MonthlyReconcileTable`
 * (`selectable`) — même barre d'action que sur la page Banques.
 *
 * L'année est pilotée par le sélecteur global du dashboard (prop `year`) —
 * pas de sélecteur local ici, pour éviter que l'en-tête du dashboard et ce
 * tableau affichent deux années différentes en même temps. Si le sélecteur
 * global pointe sur une année future, la vue peut légitimement être vide :
 * un relevé officiel n'existe que pour le passé.
 */
export function MonthlyReconcileView({ year }: { year: number }) {
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setError('');
    monthlyBalancesAPI
      .reconciliation(year)
      .then((v) => {
        if (cancelled) return;
        setView(v);
        setError('');
      })
      .catch((e) => {
        if (cancelled) return;
        setView(null);
        setError((e as Error).message || 'Erreur réseau');
      });
    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-[var(--muted)]">
          Couverture <strong className="text-[var(--text)]">{view?.coverage ?? '—'}</strong> mois
        </span>
      </div>

      {error && <p className="text-xs text-red-600">❌ {error}</p>}
      {view ? (
        <MonthlyReconcileTable view={view} selectable />
      ) : !error ? (
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      ) : null}

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <Link href="/banking#rappro-mensuel" className="text-xs font-semibold text-[var(--accent)] hover:underline">
          Déposer un relevé →
        </Link>
        <span className="ml-1.5 text-[11px] text-[var(--muted)]">(page Banques)</span>
      </div>
    </div>
  );
}
