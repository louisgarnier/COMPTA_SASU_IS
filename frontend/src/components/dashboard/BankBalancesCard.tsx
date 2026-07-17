'use client';

import { useState } from 'react';
import { Card } from '@/components/ui';
import { BalancesAtDate } from '@/components/dashboard/BalancesAtDate';
import { MonthlyReconcileView } from '@/components/dashboard/MonthlyReconcileView';

type Tab = 'soldes' | 'rappro';

const TABS: { id: Tab; label: string }[] = [
  { id: 'soldes', label: 'Soldes à une date' },
  { id: 'rappro', label: 'Rapprochement mensuel' },
];

/**
 * Carte « Soldes bancaires » du dashboard : deux lectures du même sujet.
 * — « Soldes à une date » : reconstruction à la date choisie.
 * — « Rapprochement mensuel » : officiel vs reconstitué, 12 mois (lecture seule).
 * L'onglet rappro n'est monté qu'à son ouverture : le dashboard ne paie pas
 * son appel réseau tant qu'on ne le demande pas.
 */
export function BankBalancesCard({ year }: { year?: number }) {
  const [tab, setTab] = useState<Tab>('soldes');
  const curYear = new Date().getFullYear();
  const selYear = year && year <= curYear ? year : curYear;

  return (
    <Card>
      <div className="mb-3 inline-flex gap-1 rounded-xl bg-gray-100 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              tab === t.id
                ? 'bg-white text-[var(--accent)] shadow-sm'
                : 'text-[var(--muted)] hover:text-[var(--text)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'soldes' ? <BalancesAtDate year={year} /> : <MonthlyReconcileView year={selYear} />}
    </Card>
  );
}
