'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { MonthlyReconcileTable } from '@/components/MonthlyReconcileTable';

/**
 * Onglet « Rapprochement mensuel » du dashboard — consultation seule
 * (maquette variante A, validée 2026-07-17). Le dépôt de relevé, la sélection
 * et l'envoi restent sur la page Banques : ici on regarde, on n'écrit pas.
 */
export function MonthlyReconcileView({ year: initialYear }: { year: number }) {
  const [year, setYear] = useState(initialYear);
  const currentYear = new Date().getFullYear();
  const yearOptions = [currentYear - 2, currentYear - 1, currentYear];
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
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
        <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
          {yearOptions.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => setYear(y)}
              className={`border-r border-[var(--border)] px-3 py-1 text-xs font-semibold last:border-r-0 ${
                y === year ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--text)] hover:bg-gray-50'
              }`}
            >
              {y}
            </button>
          ))}
        </div>
        <span className="text-xs text-[var(--muted)]">
          Couverture <strong className="text-[var(--text)]">{view?.coverage ?? '—'}</strong> mois
        </span>
      </div>

      {error && <p className="text-xs text-red-600">❌ {error}</p>}
      {view ? (
        <MonthlyReconcileTable view={view} />
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
