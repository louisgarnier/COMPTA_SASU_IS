'use client';

import { useEffect, useState } from 'react';
import { dashboardAPI } from '@/api/client';
import { PageTitle, Card, Empty } from '@/components/ui';
import { eur, MONTH_LABELS } from '@/lib/format';

type CatRow = { category: string; by_month: (string | number)[]; total_eur: string | number };
type Detail = {
  year: number;
  months: { month: string; revenue_eur: string; charges_eur: string; result_eur: string }[];
  totals: { revenue_eur: string; charges_eur: string; result_eur: string };
  charges_by_category: CatRow[];
};

const CUR_YEAR = new Date().getFullYear();
const YEARS = [CUR_YEAR - 1, CUR_YEAR];

/**
 * P&L annuel détaillé (clôture) : produits/charges/résultat par mois +
 * charges par catégorie × mois. Imprimable (bouton → window.print).
 */
export default function PnlDetailPage() {
  const [year, setYear] = useState(CUR_YEAR);
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    dashboardAPI
      .pnlDetail(year)
      .then((d) => setData(d as Detail))
      .catch((e) => setError((e as Error).message));
  }, [year]);

  if (error) return <Empty>❌ {error}</Empty>;
  if (!data) return <p className="text-sm text-[var(--muted)]">Chargement…</p>;

  const n = (v: string | number) => Number(v) || 0;

  return (
    <div className="print:bg-white">
      <div className="print:hidden">
        <PageTitle
          title="P&L annuel détaillé"
          subtitle="Produits, charges par catégorie et résultat — vue engagée (payées + émises), prête pour l'expert-comptable."
          action={
            <div className="flex items-center gap-2">
              <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
                {YEARS.map((y) => (
                  <button
                    key={y}
                    onClick={() => setYear(y)}
                    className={`border-r border-[var(--border)] px-3 py-1.5 text-sm font-semibold last:border-r-0 ${
                      y === year ? 'bg-[var(--accent)] text-white' : 'bg-white hover:bg-gray-50'
                    }`}
                  >
                    {y}
                  </button>
                ))}
              </div>
              <button
                onClick={() => window.print()}
                className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                🖨 Imprimer / PDF
              </button>
            </div>
          }
        />
      </div>
      <h1 className="hidden print:block print:text-lg print:font-bold">P&L {data.year} — LGC</h1>

      <Card className="mb-6 overflow-x-auto p-0 print:border-0 print:shadow-none">
        <table className="w-full text-[12px] tabular-nums">
          <thead>
            <tr className="text-right text-[10px] uppercase text-[var(--muted)]">
              <th className="px-3 py-2 text-left font-medium">EUR</th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="px-2 py-2 font-medium">{m}</th>
              ))}
              <th className="px-3 py-2 font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-[var(--border)]">
              <td className="px-3 py-1.5 font-medium">Produits</td>
              {data.months.map((m) => (
                <td key={m.month} className="px-2 py-1.5 text-right text-[var(--pos)]">
                  {n(m.revenue_eur) ? Math.round(n(m.revenue_eur)).toLocaleString('fr-FR') : '—'}
                </td>
              ))}
              <td className="px-3 py-1.5 text-right font-bold text-[var(--pos)]">{eur(data.totals.revenue_eur)}</td>
            </tr>
            <tr className="border-t border-[var(--border)]">
              <td className="px-3 py-1.5 font-medium">Charges</td>
              {data.months.map((m) => (
                <td key={m.month} className="px-2 py-1.5 text-right text-[var(--neg)]">
                  {n(m.charges_eur) ? Math.round(Math.abs(n(m.charges_eur))).toLocaleString('fr-FR') : '—'}
                </td>
              ))}
              <td className="px-3 py-1.5 text-right font-bold text-[var(--neg)]">
                {eur(Math.abs(n(data.totals.charges_eur)))}
              </td>
            </tr>
            <tr className="border-t-2 border-[var(--border)] font-semibold">
              <td className="px-3 py-1.5">Résultat</td>
              {data.months.map((m) => (
                <td key={m.month} className="px-2 py-1.5 text-right">
                  {n(m.result_eur) ? Math.round(n(m.result_eur)).toLocaleString('fr-FR') : '—'}
                </td>
              ))}
              <td className="px-3 py-1.5 text-right font-bold">{eur(data.totals.result_eur)}</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card className="overflow-x-auto p-0 print:border-0 print:shadow-none">
        <div className="border-b border-[var(--border)] px-4 py-3 text-sm font-semibold">
          Charges par catégorie <span className="font-normal text-[var(--muted)]">(nettes des remboursements, EUR réel prioritaire)</span>
        </div>
        <table className="w-full text-[12px] tabular-nums">
          <thead>
            <tr className="text-right text-[10px] uppercase text-[var(--muted)]">
              <th className="px-3 py-2 text-left font-medium">Catégorie</th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="px-2 py-2 font-medium">{m}</th>
              ))}
              <th className="px-3 py-2 font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.charges_by_category.map((r) => (
              <tr key={r.category} className="border-t border-[var(--border)]">
                <td className="px-3 py-1.5">{r.category}</td>
                {r.by_month.map((v, i) => (
                  <td key={i} className="px-2 py-1.5 text-right">
                    {n(v) ? Math.round(n(v)).toLocaleString('fr-FR') : '—'}
                  </td>
                ))}
                <td className="px-3 py-1.5 text-right font-semibold">{eur(r.total_eur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="mt-3 text-xs text-[var(--muted)] print:hidden">
        💡 Combine avec l'export CSV des transactions (page Transactions) pour le dossier complet de clôture.
      </p>
    </div>
  );
}
