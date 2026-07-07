'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { href: '/forecast', label: 'Heures & jours' },
  { href: '/invoices', label: 'Factures' },
];

/** Barre de sous-onglets de la section Facturation (Heures & jours / Factures). */
export function FacturationTabs() {
  const pathname = usePathname();
  return (
    <div className="mb-4 inline-flex gap-1 rounded-xl bg-gray-100 p-1">
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
              active
                ? 'bg-white text-[var(--accent)] shadow-sm'
                : 'text-[var(--muted)] hover:text-[var(--text)]'
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
