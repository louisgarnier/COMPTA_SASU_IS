'use client';

import { Fragment, useEffect, useState } from 'react';
import { balanceDocsAPI, monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { money } from '@/lib/format';
import { MOIS, MonthlyReconcileTable } from '@/components/MonthlyReconcileTable';

type ExtractedRow = { account_uid: string; currency: string; amount: string; matched?: boolean; hint?: string };

export function MonthlyReconcileCard({ year: initialYear }: { year: number }) {
  const [year, setYear] = useState(initialYear);
  const currentYear = new Date().getFullYear();
  const yearOptions = [currentYear - 2, currentYear - 1, currentYear];
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [proposal, setProposal] = useState<ExtractedRow[] | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
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
      setPendingFile(files[0]);
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
    let docId: number | undefined;
    if (pendingFile) {
      try {
        const doc = await balanceDocsAPI.upload(pendingFile, {
          period_year: year,
          period_month: month,
          label: `${provider} ${year}-${String(month).padStart(2, '0')}`,
        });
        docId = doc?.id;
      } catch {
        // archivage best-effort : on continue sans docId, les soldes doivent
        // quand même s'enregistrer.
      }
    }
    try {
      const items = proposal.map((p) => ({ account_uid: p.account_uid, balance: p.amount }));
      const updated = await monthlyBalancesAPI.confirm(year, month, items, docId);
      setProposal(null);
      setPendingFile(null);
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
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Rapprochement mensuel officiel</h3>
        <div className="flex items-center gap-3">
          <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
            {yearOptions.map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => setYear(y)}
                className={`border-r border-[var(--border)] px-3 py-1.5 text-sm font-semibold last:border-r-0 ${
                  y === year ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--text)] hover:bg-gray-50'
                }`}
              >
                {y}
              </button>
            ))}
          </div>
          <span className="text-sm text-[var(--muted)]">
            Couverture <strong>{view.coverage}</strong> mois
          </span>
        </div>
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
          accept={provider === 'qonto' ? '.pdf,.csv,application/pdf,text/csv,text/plain' : '.pdf,application/pdf'}
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
      <MonthlyReconcileTable view={view} selectable />
    </Card>
  );
}
