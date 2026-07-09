'use client';

import { Card } from '@/components/ui';
import { PnlSummary } from '@/components/dashboard/PnlWidget';
import { eur } from '@/lib/format';

const num = (v: string | number | undefined) => {
  const n = typeof v === 'string' ? parseFloat(v) : v ?? 0;
  return Number.isFinite(n) ? n : 0;
};

/**
 * « Distributions & IS » — le parcours annuel du dirigeant : ce que je peux
 * me verser (distribuable restant) et où j'en suis de l'IS (estimé vs payé).
 * 100 % dérivé des transactions catégorisées (distribution / is_payment).
 */
export function DistributionsCard({ data }: { data: PnlSummary }) {
  const verse = num(data.distributed_this_year_eur);
  const reste = num(data.remaining_distributable_eur ?? data.distributable_eur);
  const isEstime = num(data.is_estimate_eur);
  const isPaye = num((data as { is_paid_eur?: string | number }).is_paid_eur);
  const isReste = isEstime - isPaye;
  return (
    <Card>
      <div className="mb-3 text-sm font-semibold">Distributions & IS</div>
      <div className="flex flex-col gap-2 text-sm tabular-nums">
        <div className="rounded-lg bg-emerald-50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-emerald-700">Distribuable (restant)</div>
          <div className="text-lg font-bold text-emerald-800">{eur(reste)}</div>
          {verse > 0 && (
            <div className="text-[11px] text-emerald-700">déjà versé cet exercice : {eur(verse)}</div>
          )}
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">IS de l'exercice</div>
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] text-[var(--muted)]">estimé</span>
            <b>{eur(isEstime)}</b>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] text-[var(--muted)]">payé (acomptes/solde)</span>
            <b>{eur(isPaye)}</b>
          </div>
          <div className="mt-1 flex items-baseline justify-between border-t border-[var(--border)] pt-1">
            <span className="text-[11px] font-medium">reste à provisionner</span>
            <b className={isReste > 0 ? 'text-[var(--neg)]' : 'text-[var(--pos)]'}>{eur(isReste)}</b>
          </div>
        </div>
      </div>
      <p className="mt-2 text-[11px] text-[var(--muted)]">
        Alimenté par tes catégories « Distribution » et « Paiement IS » — catégorise les virements
        DGFIP d'IS dans « IS payé » pour que le suivi reste juste.
      </p>
    </Card>
  );
}
