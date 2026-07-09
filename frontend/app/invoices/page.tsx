'use client';

import { useEffect, useMemo, useState } from 'react';
import { invoicesAPI, settingsAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { FacturationTabs } from '@/components/FacturationTabs';
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
  amount_eur_received: number | null;
  variance_eur: number | null;
}

interface Tx {
  id: number;
  booked_date: string | null;
  amount: number;
  currency: string;
  counterparty: string;
  description: string;
  amount_eur: number | null;
}

const TODAY = new Date();

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
  const [cands, setCands] = useState<Record<number, Tx[]>>({});
  const [matching, setMatching] = useState<number | null>(null);
  const [nextNumber, setNextNumber] = useState<string>('');
  const [numMsg, setNumMsg] = useState<string>('');
  const [numDraft, setNumDraft] = useState<Record<number, string>>({});

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [inv, settings] = await Promise.all([
        invoicesAPI.list() as Promise<Invoice[]>,
        settingsAPI.get() as Promise<{ next_invoice_number: number | string }>,
      ]);
      setInvoices(inv);
      setNextNumber(String(settings?.next_invoice_number ?? ''));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveNextNumber = async () => {
    setNumMsg('…');
    try {
      const updated = (await settingsAPI.update({
        next_invoice_number: Number(nextNumber),
      })) as { next_invoice_number: number | string };
      setNextNumber(String(updated.next_invoice_number));
      setNumMsg('✅ enregistré');
      setTimeout(() => setNumMsg(''), 2000);
    } catch (e) {
      setNumMsg(`❌ ${(e as Error).message}`);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totals = useMemo(() => {
    const eur = (i: Invoice) => Number(i.amount_eur_forecast || 0);
    // Payées : EUR réellement encaissé (même valeur que la colonne « Encaissé »
    // et que le P&L) ; repli prévisionnel si le FX réel n'est pas encore alloué.
    const eurPaid = (i: Invoice) => Number(i.amount_eur_received ?? i.amount_eur_forecast ?? 0);
    const paid = invoices.filter((i) => i.status === 'paid');
    const due = invoices.filter((i) => i.status === 'due');
    const forecast = invoices.filter((i) => i.status === 'forecast');
    return {
      paidSum: paid.reduce((s, i) => s + eurPaid(i), 0), paidCount: paid.length,
      dueSum: due.reduce((s, i) => s + eur(i), 0), dueCount: due.length,
      fcSum: forecast.reduce((s, i) => s + eur(i), 0), fcCount: forecast.length,
    };
  }, [invoices]);

  // Correction manuelle du n° d'une facture émise (commit au blur / Entrée).
  const saveNum = async (i: Invoice) => {
    const draft = (numDraft[i.id] ?? '').trim();
    if (!draft || draft === i.number) {
      setNumDraft((d) => { const n = { ...d }; delete n[i.id]; return n; });
      return;
    }
    try {
      await invoicesAPI.update(i.id, { number: draft });
      setNumDraft((d) => { const n = { ...d }; delete n[i.id]; return n; });
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [i.id]: `❌ ${(e as Error).message}` }));
    }
  };

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

  // Repasse une facture émise en prévision (numéro rendu au compteur).
  // Refusé par le backend si ce n'est pas le dernier numéro (trou de séquence).
  const rollback = async (i: Invoice) => {
    if (!window.confirm(
      `Repasser la facture n°${i.number} en prévision ?\n` +
      `Le numéro sera rendu au compteur et les dates d'émission/échéance effacées.`,
    )) return;
    try {
      await invoicesAPI.rollback(i.id);
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [i.id]: `❌ ${(e as Error).message}` }));
    }
  };

  // Génère le PDF (WeasyPrint côté serveur) puis l'ouvre.
  const downloadPdf = async (i: Invoice) => {
    setMsg((m) => ({ ...m, [i.id]: 'PDF…' }));
    try {
      await invoicesAPI.generatePdf(i.id);
      setMsg((m) => ({ ...m, [i.id]: '' }));
      window.open(invoicesAPI.downloadUrl(i.id), '_blank');
    } catch (e) {
      setMsg((m) => ({ ...m, [i.id]: `❌ ${(e as Error).message}` }));
    }
  };

  const openMatch = async (id: number) => {
    if (matching === id) {
      setMatching(null);
      return;
    }
    setMatching(id);
    try {
      const list = (await invoicesAPI.candidates(id)) as Tx[];
      setCands((c) => ({ ...c, [id]: list }));
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const reconcile = async (id: number, txId: number) => {
    try {
      await invoicesAPI.reconcile(id, txId);
      setMatching(null);
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const unreconcile = async (id: number) => {
    try {
      await invoicesAPI.unreconcile(id);
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const remove = async (i: Invoice) => {
    const label = i.status === 'forecast' ? `la prévision de ${i.client_name}` : `la facture ${i.number}`;
    const extra =
      i.status === 'paid'
        ? '\n\nElle est rapprochée : la transaction bancaire liée sera libérée (elle redeviendra disponible au rapprochement).'
        : '';
    if (!window.confirm(`Supprimer ${label} ?${extra}`)) return;
    try {
      await invoicesAPI.remove(i.id);
      await load();
    } catch (e) {
      setMsg((m) => ({ ...m, [i.id]: `❌ ${(e as Error).message}` }));
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
      <FacturationTabs />
      <PageTitle
        title="Facturation — Factures"
        subtitle="Cycle de vie : prévision → à encaisser → payée"
        action={
          <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-gray-50 px-3 py-2 text-sm">
            <span className="text-[var(--muted)]">Prochain n° de facture</span>
            <input
              type="number"
              value={nextNumber}
              onChange={(e) => setNextNumber(e.target.value)}
              aria-label="Prochain numéro de facture"
              className="w-20 rounded-md border border-[var(--accent)] px-2 py-1 text-right font-semibold outline-none"
            />
            <button
              onClick={saveNextNumber}
              className="rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              OK
            </button>
            {numMsg && <span className="text-xs text-[var(--muted)]">{numMsg}</span>}
          </div>
        }
      />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label={`À encaisser (${totals.dueCount})`} value={money(totals.dueSum, 'EUR')} tone="neg" />
        <StatCard label={`Payées (${totals.paidCount})`} value={money(totals.paidSum, 'EUR')} tone="pos" />
        <StatCard label={`Prévisions (${totals.fcCount})`} value={money(totals.fcSum, 'EUR')} />
      </div>

      <p className="mb-4 text-sm text-[var(--muted)]">
        💡 Les factures naissent des saisies dans <a href="/forecast" className="text-[var(--accent)] underline">Heures &amp; jours</a>.
        « Générer » attribue un numéro (depuis le compteur ci-dessus) + les dates et passe la facture à « À encaisser ».
        Règle le compteur sur ton 1ᵉʳ numéro <b>avant</b> de générer une série de factures passées.
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
                <th className="px-4 py-3 text-right font-medium">€ (prév.)</th>
                <th className="px-4 py-3 text-right font-medium">Encaissé / écart</th>
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
                      {i.status === 'forecast' ? (
                        <span className="text-[var(--muted)]">—</span>
                      ) : (
                        <input
                          value={numDraft[i.id] ?? i.number}
                          onChange={(e) => setNumDraft((d) => ({ ...d, [i.id]: e.target.value }))}
                          onBlur={() => saveNum(i)}
                          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          aria-label={`N° facture ${i.number}`}
                          title="Cliquer pour corriger le n° de facture"
                          className="w-24 rounded-md border border-transparent bg-transparent px-1.5 py-1 font-medium tabular outline-none hover:border-[var(--border)] focus:border-[var(--accent)]"
                        />
                      )}
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
                    <td className="px-4 py-3 text-right tabular">
                      {i.status === 'paid' && i.amount_eur_received != null ? (
                        <div>
                          <div>{money(i.amount_eur_received, 'EUR')}</div>
                          {i.variance_eur != null && (
                            <div className={`text-xs ${Number(i.variance_eur) < 0 ? 'text-[var(--neg)]' : 'text-[var(--pos)]'}`}>
                              {Number(i.variance_eur) >= 0 ? '+' : ''}{money(i.variance_eur, 'EUR')}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-[var(--muted)]">—</span>
                      )}
                    </td>
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
                            <button
                              onClick={() => downloadPdf(i)}
                              title="Générer et télécharger le PDF"
                              className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium hover:border-[var(--accent)]"
                            >
                              PDF
                            </button>
                            {i.status === 'paid' ? (
                              <button
                                onClick={() => unreconcile(i.id)}
                                className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--neg)] hover:bg-red-50"
                              >
                                Annuler rappr.
                              </button>
                            ) : (
                              <>
                                <button
                                  onClick={() => openMatch(i.id)}
                                  className="rounded-lg border border-[var(--accent)] px-3 py-1 text-xs font-medium text-[var(--accent)] hover:bg-blue-50"
                                >
                                  {matching === i.id ? 'Fermer' : 'Rapprocher'}
                                </button>
                                <button
                                  onClick={() => rollback(i)}
                                  title="Repasser en prévision (numéro rendu au compteur — dernier numéro émis uniquement)"
                                  className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium hover:border-[var(--accent)]"
                                >
                                  ↩ Prévision
                                </button>
                              </>
                            )}
                          </>
                        )}
                        <button
                          onClick={() => remove(i)}
                          title="Supprimer"
                          className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--neg)] hover:bg-red-50"
                        >
                          Supprimer
                        </button>
                        {msg[i.id] && <span className="text-xs text-[var(--neg)]">{msg[i.id]}</span>}
                      </div>
                      {matching === i.id && (
                        <div className="mt-2 rounded-lg border border-[var(--border)] bg-gray-50 p-2">
                          <div className="mb-1 text-xs font-medium text-[var(--muted)]">
                            Transaction à rapprocher (revenus non liés) :
                          </div>
                          {(cands[i.id] ?? []).length === 0 ? (
                            <div className="text-xs text-[var(--muted)]">Aucune transaction candidate.</div>
                          ) : (
                            <div className="flex flex-col gap-1">
                              {(cands[i.id] ?? []).slice(0, 6).map((t) => (
                                <button
                                  key={t.id}
                                  onClick={() => reconcile(i.id, t.id)}
                                  className="flex items-center justify-between rounded-md border border-[var(--border)] bg-white px-2 py-1 text-left text-xs hover:border-[var(--accent)]"
                                >
                                  <span>
                                    {t.booked_date ? dateFR(t.booked_date) : '—'} · {t.counterparty || t.description || 'tx'}
                                  </span>
                                  <span className="tabular font-medium">{money(t.amount, t.currency)}</span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
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
