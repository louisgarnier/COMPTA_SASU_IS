'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

type Leaf = { href: string; label: string; icon: string };
type Group = { group: string; icon: string; children: Leaf[] };
type Item = Leaf | Group;

const ITEMS: Item[] = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/transactions', label: 'Transactions', icon: '💳' },
  { href: '/categories', label: 'Catégories', icon: '🏷️' },
  {
    group: 'Facturation',
    icon: '🧾',
    children: [
      { href: '/forecast', label: 'Heures & jours', icon: '⏱️' },
      { href: '/invoices', label: 'Factures', icon: '📄' },
    ],
  },
  { href: '/fx', label: 'FX / Conversions', icon: '💱' },
  { href: '/pnl', label: 'P&L annuel', icon: '📑' },
  { href: '/clients', label: 'Clients', icon: '🧑‍💼' },
  { href: '/placements', label: 'Placements', icon: '💼' },
  { href: '/banking', label: 'Banques', icon: '🏦' },
  { href: '/settings', label: 'Réglages', icon: '⚙️' },
];

export function Nav() {
  const pathname = usePathname();
  // Drawer mobile : fermé par défaut, se referme à chaque navigation.
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  const leafClass = (active: boolean) =>
    `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
      active
        ? 'bg-blue-50 font-medium text-[var(--accent)]'
        : 'text-[var(--text)] hover:bg-gray-50'
    }`;

  const navItems = (
    <nav className="flex flex-col gap-1">
      {ITEMS.map((item) => {
        if ('group' in item) {
          const groupActive = item.children.some((c) => isActive(c.href));
          return (
            <div key={item.group} className="mt-1">
              <div
                className={`flex items-center gap-2 px-3 py-2 text-sm font-semibold ${
                  groupActive ? 'text-[var(--accent)]' : 'text-[var(--text)]'
                }`}
              >
                <span aria-hidden>{item.icon}</span>
                {item.group}
              </div>
              <div className="ml-3 flex flex-col gap-1 border-l border-[var(--border)] pl-2">
                {item.children.map((c) => (
                  <Link key={c.href} href={c.href} className={leafClass(isActive(c.href))}>
                    <span aria-hidden>{c.icon}</span>
                    {c.label}
                  </Link>
                ))}
              </div>
            </div>
          );
        }
        return (
          <Link key={item.href} href={item.href} className={leafClass(isActive(item.href))}>
            <span aria-hidden>{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const brand = (
    <div className="px-3">
      <div className="text-xl font-bold tracking-tight">LGC</div>
      <div className="text-xs text-[var(--muted)]">Compta SASU</div>
    </div>
  );

  return (
    <>
      {/* Desktop : sidebar fixe (≥ lg). */}
      <aside className="hidden w-56 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] px-3 py-5 lg:block">
        <div className="mb-6">{brand}</div>
        {navItems}
      </aside>

      {/* Mobile : barre supérieure + hamburger (< lg). */}
      <div className="fixed inset-x-0 top-0 z-40 flex items-center justify-between border-b border-[var(--border)] bg-[var(--panel)] px-4 py-2.5 lg:hidden">
        {brand}
        <button
          onClick={() => setOpen(true)}
          aria-label="Ouvrir le menu"
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-lg leading-none"
        >
          ☰
        </button>
      </div>

      {/* Mobile : drawer coulissant + voile. */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 w-64 overflow-y-auto border-r border-[var(--border)] bg-[var(--panel)] px-3 py-5 shadow-xl">
            <div className="mb-6 flex items-center justify-between">
              {brand}
              <button
                onClick={() => setOpen(false)}
                aria-label="Fermer le menu"
                className="rounded-lg px-2 py-1 text-lg leading-none text-[var(--muted)]"
              >
                ✕
              </button>
            </div>
            {navItems}
          </aside>
        </div>
      )}
    </>
  );
}
