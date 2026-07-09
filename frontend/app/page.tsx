'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { treasuryAPI, dashboardAPI, transactionsAPI } from '@/api/client';
import { PageTitle, StatCard } from '@/components/ui';
import { eur } from '@/lib/format';
import { CashflowChart, CashflowData } from '@/components/dashboard/CashflowChart';
import { BalanceChart, BalanceData } from '@/components/dashboard/BalanceChart';
import { PnlWidget, PnlSummary } from '@/components/dashboard/PnlWidget';
import {
  InvoiceTimeline,
  OpenInvoices,
  InvoiceTimelineData,
} from '@/components/dashboard/InvoiceTimeline';
import { TreasuryBridge } from '@/components/dashboard/TreasuryBridge';
import { BalancesAtDate } from '@/components/dashboard/BalancesAtDate';

const CUR_YEAR = new Date().getFullYear();
// N-1 inclus : l'exercice précédent (P&L, IS) reste consultable après la clôture.
const YEARS = [CUR_YEAR - 1, CUR_YEAR, CUR_YEAR + 1, CUR_YEAR + 2];

type Treasury = { bank_total_eur: string | number; total_eur: string | number };

export default function DashboardPage() {
  const [year, setYear] = useState(CUR_YEAR);
  const [treasury, setTreasury] = useState<Treasury | null>(null);
  const [cashflow, setCashflow] = useState<CashflowData | null>(null);
  const [balance, setBalance] = useState<BalanceData | null>(null);
  const [pnl, setPnl] = useState<PnlSummary | null>(null);
  const [invoices, setInvoices] = useState<InvoiceTimelineData | null>(null);
  const [uncategorized, setUncategorized] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([
      treasuryAPI.get(),
      dashboardAPI.cashflow(year),
      dashboardAPI.balanceTimeline(year),
      dashboardAPI.pnlSummary(year),
      dashboardAPI.invoiceTimeline(),
    ])
      .then(([t, cf, bal, p, inv]) => {
        setTreasury(t);
        setCashflow(cf);
        setBalance(bal);
        setPnl(p);
        setInvoices(inv);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
    // Compteur « à catégoriser » — non bloquant : le P&L paraît faux en silence
    // tant que des sorties ne sont pas triées, donc on le signale ici.
    transactionsAPI
      .list({ uncategorized: true })
      .then((rows) => setUncategorized(rows.length))
      .catch(() => setUncategorized(0));
  }, [year]);

  const yearPicker = (
    <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
      {YEARS.map((y) => (
        <button
          key={y}
          onClick={() => setYear(y)}
          className={`border-r border-[var(--border)] px-3 py-1.5 text-sm font-semibold last:border-r-0 ${
            y === year ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--text)] hover:bg-gray-50'
          }`}
        >
          {y}
        </button>
      ))}
    </div>
  );

  if (loading) {
    return (
      <div>
        <PageTitle title="Dashboard" subtitle={`Vue d'ensemble tréso ${year}`} action={yearPicker} />
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div>
        <PageTitle title="Dashboard" subtitle={`Vue d'ensemble tréso ${year}`} action={yearPicker} />
        <p className="text-sm text-[var(--neg)]">❌ Erreur : {error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageTitle title="Dashboard" subtitle={`Vue d'ensemble tréso ${year} — réel + prévision`} action={yearPicker} />

      {uncategorized > 0 && (
        <Link
          href="/transactions"
          className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 hover:bg-amber-100"
        >
          <span>
            ⚠️ <b>{uncategorized} transaction{uncategorized > 1 ? 's' : ''} à catégoriser</b> — le
            P&L (charges) est incomplet tant qu'elles ne sont pas triées.
          </span>
          <span className="font-semibold">Trier →</span>
        </Link>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        {/* Décision produit : pilotage cash = banques (hors placements) ;
            le patrimoine total (placements incl.) est l'autre vue, à part. */}
        <StatCard label="Trésorerie (hors placements)" value={eur(treasury?.bank_total_eur)} tone="pos" />
        <StatCard label="Patrimoine total (placements incl.)" value={eur(treasury?.total_eur)} />
        <StatCard label="Résultat P&L" value={eur(pnl?.result_eur)} tone="pos" />
        <StatCard label="IS (réalisé à date)" value={eur(pnl?.is_estimate_eur)} />
        <StatCard label="Factures en attente" value={eur(invoices?.outstanding_eur)} />
      </div>

      {cashflow && <CashflowChart data={cashflow} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {balance && <BalanceChart data={balance} />}
        {pnl && <PnlWidget data={pnl} />}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TreasuryBridge year={year} />
        <BalancesAtDate year={year} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {invoices && <InvoiceTimeline data={invoices} />}
        {invoices && <OpenInvoices data={invoices} />}
      </div>
    </div>
  );
}
