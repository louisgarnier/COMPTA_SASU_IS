'use client';

import { useEffect, useState } from 'react';
import { dashboardAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { money, eur, dateFR } from '@/lib/format';

type Part = { date: string | null; foreign: string; rate: string };
type Conversion = { date: string | null; currency: string; foreign: string; eur: string; rate: string };
type InvoiceRow = {
  invoice_number: string | null;
  month: string | null;
  client_code: string | null;
  currency: string;
  native: string;
  date_received: string | null;
  rate: string;
  eur_received: string;
  composite: boolean;
  parts: Part[];
};
type Totals = Record<string, { converted_foreign: string; income_foreign: string; realized_eur: string }>;
type Report = {
  conversions: Conversion[];
  invoices: InvoiceRow[];
  leftover: Record<string, string>;
  uncovered: Record<string, string>;
  totals: Totals;
};

const num = (v: string | number | null | undefined) => {
  const n = parseFloat(String(v ?? '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
};
const rate4 = (v: string) => num(v).toLocaleString('fr-FR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const nat = (v: string, cur: string) => money(v, cur);

function CcyBadge({ cur }: { cur: string }) {
  const tone = cur === 'USD' ? 'bg-blue-50 text-blue-700' : cur === 'CAD' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600';
  return <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase ${tone}`}>{cur}</span>;
}

export default function FxPage() {
  const [data, setData] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        setData((await dashboardAPI.fxConversions()) as Report);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div>
        <PageTitle title="FX / Conversions" subtitle="Taux de change réel appliqué à chaque facture" />
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div>
        <PageTitle title="FX / Conversions" subtitle="Taux de change réel appliqué à chaque facture" />
        <Empty>Erreur de chargement : {error}</Empty>
      </div>
    );
  }

  const currencies = Object.keys(data.totals);
  const composites = data.invoices.filter((i) => i.composite).length;

  return (
    <div>
      <PageTitle
        title="FX / Conversions"
        subtitle="Toutes les conversions Revolut Business, et le taux réel appliqué à chaque facture encaissée."
      />

      {/* KPIs */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {currencies.map((c) => (
          <StatCard
            key={c}
            label={`${c} converti`}
            value={money(data.totals[c].converted_foreign, c)}
            tone="neutral"
          />
        ))}
        <StatCard label="Réel / composé" value={`${data.invoices.length - composites} · ${composites}`} tone="pos" />
        <Card>
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">Reliquat exercices antérieurs (hors factures)</div>
          <div className="mt-2 text-sm font-semibold">
            {currencies.map((c) => (
              <div key={c}>{money(data.leftover[c] ?? 0, c)}</div>
            ))}
          </div>
        </Card>
      </div>

      {/* SECTION 2 — Taux appliqué à chaque facture (le cœur) */}
      <Card className="mb-6 p-0">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div className="text-sm font-semibold">Taux appliqué à chaque facture</div>
          <div className="text-xs text-[var(--muted)]">Rattachement à rebours (ancré solde 0)</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="text-left text-xs uppercase text-[var(--muted)]">
                <th className="px-4 py-2 font-medium">Facture</th>
                <th className="px-4 py-2 font-medium">Mois</th>
                <th className="px-4 py-2 font-medium">Client</th>
                <th className="px-4 py-2 text-right font-medium">Natif</th>
                <th className="px-4 py-2 font-medium">Type de taux</th>
                <th className="px-4 py-2 text-right font-medium">Taux réel</th>
                <th className="px-4 py-2 text-right font-medium">EUR reçu</th>
              </tr>
            </thead>
            <tbody>
              {data.invoices.map((i, idx) => (
                <tr key={idx} className={`border-t border-[var(--border)] ${i.composite ? 'bg-amber-50/40' : ''}`}>
                  <td className="px-4 py-2 font-medium">{i.invoice_number ? `n°${i.invoice_number}` : '—'}</td>
                  <td className="px-4 py-2">{i.month ?? '—'}</td>
                  <td className="px-4 py-2">
                    {i.client_code ?? '—'} <CcyBadge cur={i.currency} />
                  </td>
                  <td className="px-4 py-2 text-right">{nat(i.native, i.currency)}</td>
                  <td className="px-4 py-2">
                    {i.composite ? (
                      <Badge tone="warn">composé · {i.parts.length}</Badge>
                    ) : (
                      <Badge tone="pos">réel</Badge>
                    )}
                    <div className="mt-1 text-[11px] text-[var(--muted)]">
                      {i.parts.map((p, k) => (
                        <div key={k}>
                          {i.composite && <b className="text-amber-700">{num(p.foreign).toLocaleString('fr-FR')} </b>}
                          @{rate4(p.rate)}
                          {p.date ? ` (${dateFR(p.date)})` : ' (théorique)'}
                        </div>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right font-semibold">{rate4(i.rate)}</td>
                  <td className="px-4 py-2 text-right font-semibold">{eur(i.eur_received)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-[var(--border)] bg-gray-50 px-4 py-3 text-xs text-[var(--muted)]">
          💡 <b>réel</b> : la devise de la facture a été convertie par une seule transaction FX. <b>composé</b> :
          la facture est à cheval sur 2+ conversions → taux <b>pondéré</b> (détail des tranches affiché).
        </div>
      </Card>

      {/* SECTION 1 — Conversions Revolut brutes */}
      <Card className="mb-6 p-0">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div className="text-sm font-semibold">Conversions Revolut (brut)</div>
          <div className="text-xs text-[var(--muted)]">{data.conversions.length} conversions · devise → EUR</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="text-left text-xs uppercase text-[var(--muted)]">
                <th className="px-4 py-2 font-medium">Date</th>
                <th className="px-4 py-2 font-medium">Devise</th>
                <th className="px-4 py-2 text-right font-medium">Montant sorti</th>
                <th className="px-4 py-2 text-right font-medium">EUR reçu</th>
                <th className="px-4 py-2 text-right font-medium">Taux réel</th>
              </tr>
            </thead>
            <tbody>
              {data.conversions.map((c, idx) => (
                <tr key={idx} className="border-t border-[var(--border)]">
                  <td className="px-4 py-2">{c.date ? dateFR(c.date) : '—'}</td>
                  <td className="px-4 py-2"><CcyBadge cur={c.currency} /></td>
                  <td className="px-4 py-2 text-right text-[var(--neg)]">−{nat(c.foreign, c.currency)}</td>
                  <td className="px-4 py-2 text-right">{eur(c.eur)}</td>
                  <td className="px-4 py-2 text-right font-semibold">{rate4(c.rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* SECTION 3 — Reliquat */}
      <Card>
        <div className="mb-3 text-sm font-semibold">Reliquat non facturé</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {currencies.map((c) => (
            <div key={c} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="text-xs font-semibold text-amber-800">{c} reliquat (exercices antérieurs)</div>
              <div className="mt-1 text-lg font-bold text-amber-900">{money(data.leftover[c] ?? 0, c)}</div>
              <div className="mt-1 text-xs text-amber-700">
                converti après coup mais accumulé lors d'exercices antérieurs — salaire / dividendes, exclu du CA.
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-[var(--muted)]">
          Ce reliquat explique pourquoi le total converti dépasse le total encaissé sur factures.
        </p>
      </Card>
    </div>
  );
}
