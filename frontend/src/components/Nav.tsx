'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/transactions', label: 'Transactions', icon: '💳' },
  { href: '/categories', label: 'Catégories', icon: '🏷️' },
  { href: '/forecast', label: 'Forecast', icon: '📈' },
  { href: '/clients', label: 'Clients', icon: '🧑‍💼' },
  { href: '/invoices', label: 'Factures', icon: '🧾' },
  { href: '/banking', label: 'Banques', icon: '🏦' },
  { href: '/settings', label: 'Réglages', icon: '⚙️' },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] px-3 py-5">
      <div className="mb-6 px-3">
        <div className="text-xl font-bold tracking-tight">LGC</div>
        <div className="text-xs text-[var(--muted)]">Compta SASU</div>
      </div>
      <nav className="flex flex-col gap-1">
        {LINKS.map((l) => {
          const active =
            l.href === '/' ? pathname === '/' : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                active
                  ? 'bg-blue-50 font-medium text-[var(--accent)]'
                  : 'text-[var(--text)] hover:bg-gray-50'
              }`}
            >
              <span aria-hidden>{l.icon}</span>
              {l.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
