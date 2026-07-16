'use client';

import { Fragment, useEffect, useState } from 'react';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { eur, money } from '@/lib/format';

type ExtractedRow = { account_uid: string; currency: string; amount: string; matched?: boolean; hint?: string };

const MOIS = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'];

const badgeFor = (s: string) =>
  s === 'ok' ? <Badge tone="pos">✓ ok</Badge>
  : s === 'warn' ? <Badge tone="warn">⚠ écart</Badge>
  : <Badge tone="neutral">manquant</Badge>;

export function MonthlyReconcileCard({ year }: { year: number }) {
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [proposal, setProposal] = useState<ExtractedRow[] | null>(null);
  const [month, setMonth] = useState(12);
  const [provider, setProvider] = useState<'revolut' | 'qonto'>('revolut');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    monthlyBalancesAPI.reconciliation(year).then(setView).catch(() => setView(null));
  }, [year]);

  const onDrop = async (files: FileList | null) => {
    if (!files?.[0]) return;
    setError(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', files[0]);
      fd.append('provider', provider);
      fd.append('year', String(year));
      fd.append('month', String(month));
      const res = await monthlyBalancesAPI.extract(fd);
      setProposal((res.proposal ?? []).filter((p: ExtractedRow) => p.account_uid));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Échec de l’extraction');
    } finally {
      setBusy(false);
    }
  };

  const updateAmount = (idx: number, amount: string) => {
    setProposal((cur) => cur && cur.map((p, i) => (i === idx ? { ...p, amount } : p)));
  };

  const validate = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const items = proposal.map((p) => ({ account_uid: p.account_uid, balance: p.amount }));
      const updated = await monthlyBalancesAPI.confirm(year, month, items);
      setProposal(null);
      setView(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Échec de la confirmation');
    } finally {
      setBusy(false);
    }
  };

  if (!view) return <Card><p className="text-sm text-[var(--muted)]">Chargement…</p></Card>;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Rapprochement mensuel officiel</h3>
        <span className="text-sm text-[var(--muted)]">
          Couverture <strong>{view.coverage}</strong> mois
        </span>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-[var(--border)] bg-black/[0.015] p-3 text-sm">
        <span className="font-medium">Déposer un relevé</span>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as 'revolut' | 'qonto')}
          className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-xs"
        >
          <option value="revolut">Revolut</option>
          <option value="qonto">Qonto</option>
        </select>
        <select
          value={month}
          onChange={(e) => setMonth(Number(e.target.value))}
          aria-label="Mois du relevé"
          className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-xs"
        >
          {MOIS.map((_, i) => (
            <option key={i} value={i + 1}>{String(i + 1).padStart(2, '0')}</option>
          ))}
        </select>
        <input
          type="file"
          aria-label="Déposer un relevé"
          accept="application/pdf"
          disabled={busy}
          onChange={(e) => onDrop(e.target.files)}
          className="text-xs"
        />
        {busy && <span className="text-xs text-[var(--muted)]">Traitement…</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
      {proposal && (
        <div className="mb-4 rounded-lg border border-[var(--border)] p-3">
          <p className="mb-2 text-sm font-semibold">Soldes proposés</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                <th className="py-1 pr-4 font-medium">Compte</th>
                <th className="py-1 pr-4 font-medium">Devise</th>
                <th className="py-1 pr-4 text-right font-medium">Montant</th>
                <th className="py-1 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody>
              {proposal.map((p, i) => (
                <Fragment key={p.account_uid}>
                  <tr className="border-t border-[var(--border)]">
                    <td className="py-1 pr-4">{p.hint ?? p.account_uid}</td>
                    <td className="py-1 pr-4">{p.currency}</td>
                    <td className="tabular py-1 pr-4 text-right">
                      <input
                        value={p.amount}
                        onChange={(e) => updateAmount(i, e.target.value)}
                        className="w-28 rounded border border-[var(--border)] bg-transparent px-1 py-0.5 text-right"
                      />
                      <span className="ml-2 text-xs text-[var(--muted)]">{money(p.amount, p.currency)}</span>
                    </td>
                    <td className="py-1">
                      {p.matched ? <Badge tone="pos">apparié</Badge> : <Badge tone="warn">non apparié</Badge>}
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={validate}
              disabled={busy}
              className="rounded bg-black px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              Valider les {proposal.length} soldes
            </button>
            <button
              type="button"
              onClick={() => setProposal(null)}
              disabled={busy}
              className="rounded border border-[var(--border)] px-3 py-1.5 text-xs font-medium"
            >
              Annuler
            </button>
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="py-2 pr-4 font-medium">Fin de mois</th>
              <th className="py-2 pr-4 text-right font-medium">Solde officiel (€)</th>
              <th className="py-2 pr-4 text-right font-medium">Écart</th>
              <th className="py-2 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody>
            {view.months.map((m) => (
              <Fragment key={m.month}>
                <tr
                  className="cursor-pointer border-b border-[var(--border)] last:border-0 hover:bg-black/[0.02]"
                  onClick={() => setOpen(open === m.month ? null : m.month)}
                >
                  <td className="py-2 pr-4">{MOIS[m.month - 1]} {view.year}</td>
                  <td className="tabular py-2 pr-4 text-right">
                    {m.status === 'missing' ? '—' : eur(m.total_eur_official)}
                  </td>
                  <td className="tabular py-2 pr-4 text-right">
                    {m.status === 'missing' ? '—' : eur(m.total_eur_diff)}
                  </td>
                  <td className="py-2">{badgeFor(m.status)}</td>
                </tr>
                {open === m.month && m.per_account.length > 0 && (
                  <tr className="border-b border-[var(--border)] bg-black/[0.02] last:border-0">
                    <td colSpan={4} className="px-3 pb-3">
                      <table className="w-full text-xs">
                        <tbody>
                          {m.per_account.map((a) => (
                            <tr key={a.account_uid} className="border-t border-[var(--border)]">
                              <td className="py-1 pr-2">{a.currency}</td>
                              <td className="tabular py-1 pr-2 text-right">
                                {a.official == null ? '—' : eur(a.official)}
                              </td>
                              <td className="tabular py-1 pr-2 text-right">{eur(a.reconstructed)}</td>
                              <td className="tabular py-1 pr-2 text-right">
                                {a.diff == null ? '—' : eur(a.diff)}
                              </td>
                              <td className="py-1">{badgeFor(a.status)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
