'use client';

import { useEffect, useMemo, useState } from 'react';
import { treasuryAPI } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { eur, money, dateFR } from '@/lib/format';
import { isoDate, dateShortcuts } from '@/lib/dates';

type AccountRow = {
  account_uid: string;
  name: string;
  provider: string;
  currency: string;
  balance: string;
  balance_eur: string;
};
type TreasuryAt = { as_of: string | null; accounts: AccountRow[]; bank_total_eur: string };

/**
 * « Soldes bancaires à une date » — reconstruction ouverture d'exercice +
 * mouvements jusqu'à la date choisie (endpoint /api/treasury?as_of= existant).
 */
export function BalancesAtDate({ year }: { year?: number }) {
  const today = useMemo(() => new Date(), []);
  const curYear = today.getFullYear();
  const selYear = year && year <= curYear ? year : curYear;
  const [asOf, setAsOf] = useState(isoDate(today));
  const [data, setData] = useState<TreasuryAt | null>(null);
  const [error, setError] = useState('');

  // Suit le sélecteur d'année du dashboard (exercice passé → 31/12 de l'exercice).
  useEffect(() => {
    setAsOf(selYear === curYear ? isoDate(today) : `${selYear}-12-31`);
  }, [selYear, curYear, today]);

  useEffect(() => {
    treasuryAPI
      .get(asOf)
      .then((d) => setData(d as TreasuryAt))
      .catch((e) => setError((e as Error).message));
  }, [asOf]);

  const chips = dateShortcuts(today, selYear);

  return (
    <Card>
      <div className="mb-1 text-sm font-semibold">Soldes bancaires à une date</div>
      <p className="mb-3 text-[11px] text-[var(--muted)]">
        Reconstruction : ouverture d&apos;exercice + mouvements jusqu&apos;à la date choisie.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={asOf}
          max={isoDate(today)}
          aria-label="Date des soldes"
          onChange={(e) => setAsOf(e.target.value)}
          className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs outline-none focus:border-[var(--accent)]"
        />
        {chips.map((c) => (
          <button
            key={c.date}
            onClick={() => setAsOf(c.date)}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${
              asOf === c.date
                ? 'border-[var(--accent)] bg-blue-50 text-[var(--accent)]'
                : 'border-[var(--border)] text-[var(--muted)] hover:bg-gray-50'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {error && <p className="text-xs text-red-600">❌ {error}</p>}
      {data && (
        <table className="w-full text-xs tabular-nums">
          <thead>
            <tr className="text-left text-[10px] uppercase text-[var(--muted)]">
              <th className="py-1 pr-2 font-medium">Compte</th>
              <th className="py-1 pr-2 font-medium">Devise</th>
              <th className="py-1 pr-2 text-right font-medium">Solde natif</th>
              <th className="py-1 text-right font-medium">Équiv. EUR</th>
            </tr>
          </thead>
          <tbody>
            {data.accounts.map((a) => (
              <tr key={a.account_uid} className="border-t border-[var(--border)]">
                <td className="py-1 pr-2">
                  {a.name || a.provider}
                  <span className="ml-1 text-[10px] text-[var(--muted)]">…{a.account_uid.slice(-6)}</span>
                </td>
                <td className="py-1 pr-2"><Badge tone="neutral">{a.currency}</Badge></td>
                <td className="py-1 pr-2 text-right">{money(a.balance, a.currency)}</td>
                <td className="py-1 text-right">{eur(a.balance_eur)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-[var(--border)] font-semibold">
              <td colSpan={3} className="py-1.5 pr-2 text-right">Total banques ({dateFR(asOf)})</td>
              <td className="py-1.5 text-right">{eur(data.bank_total_eur)}</td>
            </tr>
          </tfoot>
        </table>
      )}
    </Card>
  );
}
