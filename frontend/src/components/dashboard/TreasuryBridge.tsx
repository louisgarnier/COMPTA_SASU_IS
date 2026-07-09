'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { dashboardAPI } from '@/api/client';
import { Card } from '@/components/ui';
import { eur, dateFR } from '@/lib/format';
import { isoDate, dateShortcuts } from '@/lib/dates';

export type BridgeLine = { key: string; label: string; amount_eur: string };
export type BridgeData = {
  year: number;
  as_of: string;
  opening_eur: string;
  lines: BridgeLine[];
  residual_eur: string;
  residual_warning: boolean;
  bank_today_eur: string;
  due_pending_eur: string;
};

const num = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : 0;
};

/**
 * « D'où vient ma trésorerie ? » — pont en cascade ouverture → banque à la
 * date choisie. 100 % dynamique : change la date, chaque ligne se recalcule et
 * le pont boucle sur le solde reconstruit à cette date. Chaque ligne est
 * CLIQUABLE → onglet Transactions pré-filtré (même logique de classement côté
 * backend : le total de la liste égale la ligne, au centime).
 */
export function TreasuryBridge({ year }: { year?: number }) {
  const today = useMemo(() => new Date(), []);
  const curYear = today.getFullYear();
  const selYear = year ?? curYear;
  const isFuture = selYear > curYear;
  const [asOf, setAsOf] = useState(isoDate(today));
  const [data, setData] = useState<BridgeData | null>(null);
  const [error, setError] = useState('');

  // Suit le sélecteur d'année du dashboard : exercice passé → pont au 31/12
  // de cet exercice ; exercice courant → aujourd'hui.
  useEffect(() => {
    setAsOf(selYear === curYear ? isoDate(today) : `${selYear}-12-31`);
  }, [selYear, curYear, today]);

  useEffect(() => {
    if (isFuture) return; // exercice futur : pas de flux, pas d'appel.
    dashboardAPI
      .treasuryBridge(asOf)
      .then((d) => setData(d as BridgeData))
      .catch((e) => setError((e as Error).message));
  }, [asOf, isFuture]);

  const chips = dateShortcuts(today, selYear);

  if (isFuture) {
    return (
      <Card>
        <div className="mb-1 text-sm font-semibold">
          D&apos;où vient ma trésorerie ?{' '}
          <span className="font-normal text-[var(--muted)]">· exercice {selYear}</span>
        </div>
        <p className="text-xs text-[var(--muted)]">
          Exercice pas encore ouvert — aucun flux bancaire. Le pont se construira à partir du
          01/01/{selYear} (ouverture à saisir dans Réglages → Soldes d&apos;ouverture, flux au fil
          des synchronisations). Pour la projection {selYear}, voir la courbe et le cashflow.
        </p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <div className="mb-1 text-sm font-semibold">D&apos;où vient ma trésorerie ?</div>
        <p className="text-xs text-red-600">❌ {error}</p>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <div className="mb-1 text-sm font-semibold">D&apos;où vient ma trésorerie ?</div>
        <p className="text-xs text-[var(--muted)]">Chargement…</p>
      </Card>
    );
  }

  const opening = num(data.opening_eur);
  const residual = num(data.residual_eur);
  const txHref = (key: string) => `/transactions?bridge=${encodeURIComponent(key)}&as_of=${data.as_of}`;

  // Cascade : positions cumulées pour dessiner les barres.
  type Row = {
    label: string; amount: number; from: number; to: number;
    kind: 'anchor' | 'pos' | 'neg'; href?: string; title?: string;
  };
  const rows: Row[] = [];
  let running = opening;
  rows.push({ label: `Ouverture 01/01/${data.year}`, amount: opening, from: 0, to: opening, kind: 'anchor' });
  for (const l of data.lines) {
    const a = num(l.amount_eur);
    rows.push({
      label: l.label, amount: a, from: running, to: running + a,
      kind: a >= 0 ? 'pos' : 'neg', href: txHref(l.key),
      title: 'Voir les transactions de cette ligne',
    });
    running += a;
  }
  rows.push({
    label: 'Frais & écarts FX (résiduel)', amount: residual,
    from: running, to: running + residual, kind: residual >= 0 ? 'pos' : 'neg',
    href: txHref('residual'),
    title: 'Résiduel calculé par différence — le lien montre les conversions FX, où vit l’essentiel de cet écart',
  });
  running += residual;
  rows.push({ label: `= Banques au ${dateFR(data.as_of)}`, amount: running, from: 0, to: running, kind: 'anchor' });

  const maxScale = Math.max(...rows.map((r) => Math.max(Math.abs(r.from), Math.abs(r.to))), 1);
  const left = (r: Row) => `${(Math.min(r.from, r.to) / maxScale) * 100}%`;
  const width = (r: Row) => `${(Math.abs(r.to - r.from) / maxScale) * 100}%`;

  const tone = (k: Row['kind']) =>
    k === 'anchor' ? 'bg-blue-600' : k === 'pos' ? 'bg-emerald-600' : 'bg-red-500';
  const valTone = (k: Row['kind'], a: number) =>
    k === 'anchor' ? 'text-blue-700' : a >= 0 ? 'text-emerald-700' : 'text-red-600';

  return (
    <Card>
      <div className="mb-1 text-sm font-semibold">
        D&apos;où vient ma trésorerie ?{' '}
        <span className="font-normal text-[var(--muted)]">· exercice {data.year}</span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={asOf}
          min={`${selYear - 1}-12-31`}
          max={selYear === curYear ? isoDate(today) : `${selYear}-12-31`}
          aria-label="Date du pont de trésorerie"
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
      <div className="flex flex-col gap-1 tabular-nums">
        {rows.map((r, i) => (
          <div key={i} className={`grid grid-cols-[minmax(150px,42%)_1fr_110px] items-center gap-2 text-xs ${
            i === rows.length - 1 ? 'mt-1 border-t border-[var(--border)] pt-1.5 font-semibold' : ''
          }`}>
            {r.href ? (
              <Link
                href={r.href}
                title={r.title}
                className="text-right text-[var(--text)] underline decoration-dotted underline-offset-2 hover:text-[var(--accent)]"
              >
                {r.amount >= 0 ? '+ ' : '− '}
                {r.label}
              </Link>
            ) : (
              <span className="text-right text-[var(--text)]">{r.label}</span>
            )}
            <span className="relative h-4 overflow-hidden rounded bg-gray-100">
              <span
                className={`absolute bottom-0.5 top-0.5 rounded-sm ${tone(r.kind)}`}
                style={{ left: left(r), width: width(r), minWidth: 2 }}
              />
            </span>
            <span className={`text-right font-semibold ${valTone(r.kind, r.amount)}`}>
              {eur(Math.abs(r.amount) < 0.005 ? 0 : r.amount)}
            </span>
          </div>
        ))}
      </div>
      {data.residual_warning && (
        <p className="mt-2 text-[11px] font-medium text-amber-700">
          ⚠ Résiduel élevé (&gt;2 % du volume) — un flux est probablement mal catégorisé.
        </p>
      )}
      <p className="mt-2 text-[11px] text-[var(--muted)]">
        💡 À venir (pas encore en banque au {dateFR(data.as_of)}) : <b>{eur(data.due_pending_eur)}</b> de
        factures émises non payées. Dividendes et placements ne sont pas des charges → résultat
        P&amp;L ≠ variation de trésorerie. Clique une ligne pour voir ses transactions.
      </p>
    </Card>
  );
}
