'use client';

import { useRef, useState } from 'react';
import { Card } from '@/components/ui';
import { BalancesAtDate } from '@/components/dashboard/BalancesAtDate';
import { MonthlyReconcileView } from '@/components/dashboard/MonthlyReconcileView';

type Tab = 'soldes' | 'rappro';

const TABS: { id: Tab; label: string }[] = [
  { id: 'soldes', label: 'Soldes à une date' },
  { id: 'rappro', label: 'Rapprochement mensuel' },
];

const tabId = (id: Tab) => `bank-balances-tab-${id}`;
const panelId = (id: Tab) => `bank-balances-panel-${id}`;

/**
 * Carte « Soldes bancaires » du dashboard : deux lectures du même sujet.
 * — « Soldes à une date » : reconstruction à la date choisie.
 * — « Rapprochement mensuel » : officiel vs reconstitué, 12 mois (lecture seule).
 * L'onglet rappro n'est monté qu'à son ouverture : le dashboard ne paie pas
 * son appel réseau tant qu'on ne le demande pas.
 *
 * Sémantique ARIA « tabs » standard : role="tablist" / role="tab" avec
 * aria-selected + aria-controls, panneau unique en role="tabpanel", et
 * navigation clavier aux flèches gauche/droite entre onglets.
 */
export function BankBalancesCard({ year }: { year?: number }) {
  const [tab, setTab] = useState<Tab>('soldes');
  const curYear = new Date().getFullYear();
  const selYear = year && year <= curYear ? year : curYear;
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ soldes: null, rappro: null });

  const focusTab = (id: Tab) => {
    setTab(id);
    tabRefs.current[id]?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const delta = e.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (index + delta + TABS.length) % TABS.length;
    focusTab(TABS[nextIndex].id);
  };

  return (
    <Card>
      <div role="tablist" className="mb-3 inline-flex gap-1 rounded-xl bg-gray-100 p-1">
        {TABS.map((t, index) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[t.id] = el;
              }}
              type="button"
              role="tab"
              id={tabId(t.id)}
              aria-selected={active}
              aria-controls={panelId(t.id)}
              tabIndex={active ? 0 : -1}
              onClick={() => setTab(t.id)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                active
                  ? 'bg-white text-[var(--accent)] shadow-sm'
                  : 'text-[var(--muted)] hover:text-[var(--text)]'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {tab === 'soldes' ? (
        <div role="tabpanel" id={panelId('soldes')} aria-labelledby={tabId('soldes')}>
          <BalancesAtDate year={year} />
        </div>
      ) : (
        <div role="tabpanel" id={panelId('rappro')} aria-labelledby={tabId('rappro')}>
          <MonthlyReconcileView year={selYear} />
        </div>
      )}
    </Card>
  );
}
