'use client';

import { useCallback, useEffect, useState } from 'react';
import { financialAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge } from '@/components/ui';
import { eur } from '@/lib/format';

type Money = string | number;

type Statement = {
  year: number;
  is_regime: string;
  app: {
    production_vendue: Money;
    charges_exploitation: Money;
    charges_by_poste: { poste: string; montant: Money }[];
    resultat_exploitation: Money;
    produits_financiers: Money;
    is_estimate: Money;
    resultat_net: Money;
  };
  accountant: {
    production_vendue: Money;
    charges_exploitation: Money;
    resultat_exploitation: Money;
    produits_financiers: Money;
    charges_financieres: Money;
    resultat_financier: Money;
    dotations_amortissements: Money;
    provision_change: Money;
    is_amount: Money;
    resultat_net: Money;
    note: string;
  } | null;
  bridge: { label: string; amount: Money; anchor?: boolean }[];
};

const YEARS = [2024, 2025, 2026];

const FIELDS: { key: string; label: string }[] = [
  { key: 'production_vendue', label: 'Production vendue (CA)' },
  { key: 'charges_exploitation', label: "Charges d'exploitation" },
  { key: 'resultat_exploitation', label: "Résultat d'exploitation" },
  { key: 'produits_financiers', label: 'Produits financiers' },
  { key: 'charges_financieres', label: 'Charges financières' },
  { key: 'resultat_financier', label: 'Résultat financier' },
  { key: 'dotations_amortissements', label: 'Dotations aux amortissements' },
  { key: 'provision_change', label: 'Provision pour perte de change' },
  { key: 'is_amount', label: 'Impôt sur les bénéfices (IS)' },
  { key: 'resultat_net', label: 'Résultat net (bénéfice)' },
];

const n = (v: Money) => Number(v ?? 0);

export default function EtatFinancierPage() {
  const [year, setYear] = useState(2025);
  const [data, setData] = useState<Statement | null>(null);
  const [error, setError] = useState('');
  const [showPostes, setShowPostes] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [saveMsg, setSaveMsg] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      setData((await financialAPI.statement(year)) as Statement);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [year]);

  useEffect(() => {
    load();
  }, [load]);

  function openEdit() {
    const acc = data?.accountant;
    const next: Record<string, string> = {};
    FIELDS.forEach((f) => {
      next[f.key] = acc ? String((acc as Record<string, Money>)[f.key] ?? '') : '';
    });
    next.note = acc?.note ?? '';
    setForm(next);
    setSaveMsg('');
    setEditing(true);
  }

  async function save() {
    setSaveMsg('Enregistrement…');
    const payload: Record<string, unknown> = { note: form.note ?? '' };
    FIELDS.forEach((f) => (payload[f.key] = Number(form[f.key]) || 0));
    try {
      await financialAPI.saveAccountant(year, payload);
      setEditing(false);
      load();
    } catch (e) {
      setSaveMsg(`❌ ${(e as Error).message}`);
    }
  }

  const app = data?.app;
  const acc = data?.accountant;
  const hasAcc = !!acc;
  const isIS = data?.is_regime === 'IS';

  return (
    <div>
      <PageTitle
        title="État financier"
        subtitle="Compte de résultat de l'app, calculé en direct — comparé au comptable pour les exercices clôturés"
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
          {YEARS.map((y) => (
            <button
              key={y}
              onClick={() => setYear(y)}
              className={`px-3 py-1.5 text-sm ${y === year ? 'bg-[var(--accent)] font-semibold text-white' : 'text-[var(--muted)] hover:bg-gray-50'}`}
            >
              {y}
            </button>
          ))}
        </div>
        {data && (
          <Badge tone={isIS ? 'pos' : 'neutral'}>
            Exercice {data.is_regime}
            {!isIS ? ' · IS 0' : ''}
          </Badge>
        )}
        {hasAcc ? (
          <Badge tone="pos">✓ Comptable validé</Badge>
        ) : (
          <span className="text-xs text-[var(--muted)]">Exercice en cours — pas encore de CdR comptable</span>
        )}
        <button
          onClick={openEdit}
          className="ml-auto rounded-lg border border-[var(--accent)] px-3 py-1.5 text-sm text-[var(--accent)] hover:bg-blue-50"
        >
          ✏️ {hasAcc ? 'Éditer' : 'Saisir'} le compte de résultat validé
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-[var(--neg)]">❌ {error}</p>}

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Production vendue (CA)" value={app ? eur(app.production_vendue) : '—'} />
        <StatCard label="Résultat net — App" value={app ? eur(app.resultat_net) : '—'} />
        {hasAcc ? (
          <StatCard
            label="Écart App − Comptable"
            value={`${n(app!.resultat_net) - n(acc!.resultat_net) >= 0 ? '+' : ''}${eur(n(app!.resultat_net) - n(acc!.resultat_net))}`}
            tone={n(app!.resultat_net) - n(acc!.resultat_net) >= 0 ? 'pos' : 'neg'}
          />
        ) : (
          <StatCard label={isIS ? 'IS estimé' : "Résultat d'exploitation"} value={app ? eur(isIS ? app.is_estimate : app.resultat_exploitation) : '—'} />
        )}
      </div>

      {/* Compte de résultat (app toujours ; comptable en surcouche) */}
      <Card>
        <div className="mb-1 text-sm font-semibold">
          Compte de résultat {year}
          {hasAcc && <span className="ml-2 font-normal text-[var(--muted)]">— App vs Comptable</span>}
        </div>
        <p className="mb-3 text-xs text-[var(--muted)]">
          {hasAcc
            ? 'Montants comptable saisis une fois par exercice, stockés (jamais en dur).'
            : "Exercice ouvert : compte de résultat calculé par l'app. Le comptable sera comparable une fois l'exercice clôturé."}
        </p>
        {app && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted)]">
                  <th className="py-2 pr-2 text-left font-semibold">Poste</th>
                  <th className="px-2 py-2 text-right font-semibold">App</th>
                  {hasAcc && <th className="px-2 py-2 text-right font-semibold">Comptable</th>}
                  {hasAcc && <th className="px-2 py-2 text-right font-semibold">Écart</th>}
                </tr>
              </thead>
              <tbody>
                <Row label="Production vendue (CA)" a={app.production_vendue} c={acc?.production_vendue} hasAcc={hasAcc} />

                <tr>
                  <td className="py-2 pr-2 text-left">
                    Charges d&apos;exploitation{' '}
                    <button onClick={() => setShowPostes((s) => !s)} className="text-xs text-[var(--accent)]">
                      {showPostes ? '▾ masquer' : `▸ ${app.charges_by_poste.length} postes`}
                    </button>
                  </td>
                  <td className="px-2 py-2 text-right">({eur(app.charges_exploitation)})</td>
                  {hasAcc && <td className="px-2 py-2 text-right">({eur(acc!.charges_exploitation)})</td>}
                  {hasAcc && (
                    <td className="px-2 py-2 text-right text-[var(--muted)]">
                      {ecart(app.charges_exploitation, acc!.charges_exploitation)}
                    </td>
                  )}
                </tr>
                {showPostes &&
                  app.charges_by_poste.map((p) => (
                    <tr key={p.poste} className="text-[var(--muted)]">
                      <td className="py-1 pl-6 pr-2 text-left text-xs">{p.poste}</td>
                      <td className="px-2 py-1 text-right text-xs">({eur(p.montant)})</td>
                      {hasAcc && <td />}
                      {hasAcc && <td />}
                    </tr>
                  ))}

                <Row label="Résultat d'exploitation" a={app.resultat_exploitation} c={acc?.resultat_exploitation} hasAcc={hasAcc} strong />

                {(n(app.produits_financiers) !== 0 || hasAcc) && (
                  <Row label="Produits financiers" a={app.produits_financiers} c={acc?.produits_financiers} hasAcc={hasAcc} />
                )}
                {hasAcc && (
                  <Row label="Résultat financier" a={0} c={acc!.resultat_financier} hasAcc={hasAcc} appDash />
                )}
                {(isIS || hasAcc) && (
                  <Row
                    label={isIS ? 'Impôt sur les bénéfices (IS estimé)' : 'Impôt sur les bénéfices'}
                    a={app.is_estimate}
                    c={acc?.is_amount}
                    hasAcc={hasAcc}
                    paren
                  />
                )}

                <Row label="Résultat net" a={app.resultat_net} c={acc?.resultat_net} hasAcc={hasAcc} strong />
              </tbody>
            </table>
            {hasAcc && (
              <p className="mt-3 text-xs text-[var(--muted)]">
                L&apos;écart de CA est un effet de <b>change</b> (comptable au taux facture, app au taux
                d&apos;encaissement) ; les charges diffèrent du <b>non-cash</b> (dotations, provisions) et du
                classement. Détail dans le pont ci-dessous.
              </p>
            )}
          </div>
        )}
      </Card>

      {/* Pont de réconciliation (seulement si comptable) */}
      {data && data.bridge.length > 0 && (
        <Card>
          <div className="mb-1 text-sm font-semibold">Pont de réconciliation — résultat net</div>
          <p className="mb-3 text-xs text-[var(--muted)]">De l&apos;app au comptable, poste à poste. Le pont se ferme au centime.</p>
          <div className="flex flex-col gap-0.5">
            {data.bridge.map((s, i) => (
              <div
                key={i}
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                  s.anchor ? 'bg-blue-50 font-semibold' : n(s.amount) < 0 ? 'bg-red-50' : 'bg-green-50'
                }`}
              >
                <span>{s.label}</span>
                <span className={`font-semibold tabular-nums ${s.anchor ? '' : n(s.amount) < 0 ? 'text-[var(--neg)]' : 'text-[var(--pos)]'}`}>
                  {n(s.amount) >= 0 && !s.anchor ? '+' : ''}
                  {eur(s.amount)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Modale de saisie */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-[var(--panel)] p-5 shadow-xl">
            <div className="mb-3 text-sm font-semibold">Compte de résultat validé — {year}</div>
            <div className="grid grid-cols-1 gap-2">
              {FIELDS.map((f) => (
                <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-[var(--muted)]">{f.label}</span>
                  <input
                    type="number"
                    step="any"
                    value={form[f.key] ?? ''}
                    onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    className="w-40 rounded-lg border border-[var(--border)] px-3 py-1.5 text-right outline-none focus:border-[var(--accent)]"
                  />
                </label>
              ))}
              <label className="mt-1 flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Note</span>
                <input
                  value={form.note ?? ''}
                  onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]"
                />
              </label>
            </div>
            {saveMsg && <p className="mt-2 text-xs">{saveMsg}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setEditing(false)} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent)]">
                Annuler
              </button>
              <button onClick={save} className="rounded-lg bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white hover:opacity-90">
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ecart(a: Money, c: Money) {
  const d = Number(a ?? 0) - Number(c ?? 0);
  return `${d >= 0 ? '+' : ''}${eur(d)}`;
}

function Row({
  label,
  a,
  c,
  hasAcc,
  strong,
  paren,
  appDash,
}: {
  label: string;
  a: Money;
  c?: Money;
  hasAcc: boolean;
  strong?: boolean;
  paren?: boolean;
  appDash?: boolean;
}) {
  const d = Number(a ?? 0) - Number(c ?? 0);
  const fmt = (v: Money) => (paren ? `(${eur(v)})` : eur(v));
  return (
    <tr className={`border-b border-gray-100 ${strong ? 'font-semibold' : ''}`}>
      <td className="py-2 pr-2 text-left">{label}</td>
      <td className="px-2 py-2 text-right">{appDash ? <span className="text-[var(--muted)]">—</span> : fmt(a)}</td>
      {hasAcc && <td className="px-2 py-2 text-right">{c == null ? '—' : fmt(c)}</td>}
      {hasAcc && (
        <td className={`px-2 py-2 text-right ${d === 0 ? '' : d > 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
          {c == null ? '' : `${d >= 0 ? '+' : ''}${eur(d)}`}
        </td>
      )}
    </tr>
  );
}
