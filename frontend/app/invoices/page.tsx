'use client';

import { useEffect, useMemo, useState } from 'react';
import { invoicesAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { money, dateFR } from '@/lib/format';

type Status = 'forecast' | 'due' | 'paid';

interface Invoice {
  id: number;
  number: string;
  client_name: string;
  month: string;
  period_label: string;
  days: number;
  hours: number;
  rate: number;
  rate_unit: string;
  currency: string;
  amount: number;
  amount_eur_forecast: number;
  issue_date: string | null;
  due_date: string | null;
  status: Status;
  paid_date: string | null;
  variance_eur: number | null;
}

const TODAY = new Date('2026-07-03T00:00:00');

// Statut effectif (overdue dérivé pour une facture 'due' échue).
function effStatus(i: Invoice): Status | 'overdue' {
  if (i.status === 'due' && i.due_date && new Date(i.due_date) < TODAY) return 'overdue';
  return i.status;
}

const LABEL: Record<string, string> = {
  forecast: 'Prévision', due: 'À encaisser', overdue: 'En retard', paid: 'Payée',
};
const TONE: Record<string, 'pos' | 'warn' | 'neutral' | 'neg'> = {
  paid: 'pos', due: 'warn', overdue: 'neg', forecast: 'neutral',
};

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState<Record<number, string>>({});

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setInvoices((await invoicesAPI.list()) as Invoice[]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totals = useMemo(() => {
    const eur = (i: Invoice) => Number(i.amount_eur_forecast || 0);
    const paid = invoices.filter((i) => i.status === 'paid');
    const due = invoices.filter((i) => i.status === 'due');
    const forecast = invoices.filter((i) => i.status === 'forecast');
    return {
      paidSum: paid.reduce((s, i) => s + eur(i), 0), paidCount: paid.length,
      dueSum: due.reduce((s, i) => s + eur(i), 0), dueCount: due.length,
      fcSum: forecast.reduce((s, i) => s + eur(i), 0), fcCount: forecast.length,
    };
  }, [invoices]);

  const generate = async (id: number) => {
    setMsg((m) => ({ ...m, [id]: 'Génération…' }));
    try {
      await invoicesAPI.generate(id);
      setMsg((m) => ({ ...m, [id]: '' }));
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const changeStatus = async (id: number, status: Status) => {
    try {
      await invoicesAPI.update(id, { status });
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  // Ordre d'affichage : dues/retard d'abord, puis prévisions, puis payées.
  const sorted = useMemo(() => {
    const rank: Record<string, number> = { overdue: 0, due: 1, forecast: 2, paid: 3 };
    return [...invoices].sort(
      (a, b) => rank[effStatus(a)] - rank[effStatus(b)] || a.month.localeCompare(b.month),
    );
  }, [invoices]);

  return (
    <div>
      <PageTitle title="Factures" subtitle="Cycle de vie : prévision → à encaisser → payée" />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label={`À encaisser (${totals.dueCount})`} value={money(totals.dueSum, 'EUR')} tone="neg" />
        <StatCard label={`Payées (${totals.paidCount})`} value={money(totals.paidSum, 'EUR')} tone="pos" />
        <StatCard label={`Prévisions (${totals.fcCount})`} value={money(totals.fcSum, 'EUR')} />
      </div>

      <p className="mb-4 text-sm text-[var(--muted)]">
        💡 Les factures naissent des prévisions saisies dans <a href="/forecast" className="text-[var(--accent)] underline">Forecast</a>.
        « Générer » attribue un numéro + les dates et passe la facture à « À encaisser ».
      </p>

      {loading ? (
        <Empty>Chargement…</Empty>
      ) : error ? (
        <Empty>❌ {error}</Empty>
      ) : invoices.length === 0 ? (
        <Empty>Aucune facture. Saisis des prévisions dans Forecast.</Empty>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                <th className="px-4 py-3 font-medium">N°</th>
                <th className="px-4 py-3 font-medium">Client</th>
                <th className="px-4 py-3 font-medium">Mois</th>
                <th className="px-4 py-3 text-right font-medium">Montant</th>
                <th className="px-4 py-3 text-right font-medium">€ (théo.)</th>
                <th className="px-4 py-3 font-medium">Échéance</th>
                <th className="px-4 py-3 font-medium">Statut</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((i) => {
                const st = effStatus(i);
                return (
                  <tr key={i.id} className="border-b border-[var(--border)] last:border-0">
                    <td className="px-4 py-3 font-medium tabular">
                      {i.status === 'forecast' ? <span className="text-[var(--muted)]">—</span> : i.number}
                    </td>
                    <td className="px-4 py-3">{i.client_name}</td>
                    <td className="px-4 py-3">
                      {i.month}
                      <div className="text-xs text-[var(--muted)]">
                        {i.rate_unit === 'hour' ? `${i.hours} h` : `${i.days} j`} @ {i.rate} {i.currency}
                        {i.rate_unit === 'hour' ? '/h' : '/j'}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular">{money(i.amount, i.currency)}</td>
                    <td className="px-4 py-3 text-right tabular text-[var(--muted)]">{money(i.amount_eur_forecast, 'EUR')}</td>
                    <td className="px-4 py-3 text-xs">{i.due_date ? dateFR(i.due_date) : '—'}</td>
                    <td className="px-4 py-3">
                      <Badge tone={TONE[st]}>{LABEL[st]}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {i.status === 'forecast' ? (
                          <button
                            onClick={() => generate(i.id)}
                            className="rounded-lg bg-[var(--accent)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
                          >
                            Générer
                          </button>
                        ) : (
                          <>
                            <a
                              href={invoicesAPI.printUrl(i.id)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium hover:border-[var(--accent)]"
                            >
                              Ouvrir la facture
                            </a>
                            <select
                              value={i.status}
                              onChange={(e) => changeStatus(i.id, e.target.value as Status)}
                              className="rounded-lg border border-[var(--border)] px-2 py-1 text-xs outline-none focus:border-[var(--accent)]"
                            >
                              <option value="due">À encaisser</option>
                              <option value="paid">Payée</option>
                            </select>
                          </>
                        )}
                        {msg[i.id] && <span className="text-xs text-[var(--neg)]">{msg[i.id]}</span>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
