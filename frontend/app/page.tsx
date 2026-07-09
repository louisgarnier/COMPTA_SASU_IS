'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { treasuryAPI, dashboardAPI, transactionsAPI, settingsAPI, Scope } from '@/api/client';
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
import { DistributionsCard } from '@/components/dashboard/DistributionsCard';

const CUR_YEAR = new Date().getFullYear();
// N-1 inclus : l'exercice précédent (P&L, IS) reste consultable après la clôture.
const YEARS = [CUR_YEAR - 1, CUR_YEAR, CUR_YEAR + 1, CUR_YEAR + 2];

type Treasury = { bank_total_eur: string | number; total_eur: string | number };

// Niveau de certitude (maquette validée 2026-07-09) : pilote P&L, IS, cashflow
// et futur de la courbe. Les widgets de STOCK (trésorerie, patrimoine, pont,
// soldes à date) restent toujours au réel.
const SCOPES: { value: Scope; label: string }[] = [
  { value: 'realized', label: 'Réalisé' },
  { value: 'engaged', label: 'Engagé' },
  { value: 'forecast', label: 'Prévisionnel' },
];
const SCOPE_NOTE: Record<Scope, string> = {
  realized: '✅ Réalisé — uniquement le concrétisé : factures payées (EUR réel) + charges réelles.',
  engaged: '📘 Engagé — + factures émises non payées (au taux théorique). Les prévisions sont ignorées.',
  forecast: '🔮 Prévisionnel — + prévisions saisies + charges projetées. Mêmes chiffres que « Heures & jours ».',
};

export default function DashboardPage() {
  const [year, setYear] = useState(CUR_YEAR);
  const [scope, setScope] = useState<Scope>('engaged');
  const [treasury, setTreasury] = useState<Treasury | null>(null);
  const [cashflow, setCashflow] = useState<CashflowData | null>(null);
  const [balance, setBalance] = useState<BalanceData | null>(null);
  const [pnl, setPnl] = useState<PnlSummary | null>(null);
  const [invoices, setInvoices] = useState<InvoiceTimelineData | null>(null);
  const [uncategorized, setUncategorized] = useState(0);
  const [lowAlertThreshold, setLowAlertThreshold] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([
      treasuryAPI.get(),
      dashboardAPI.cashflow(year, scope),
      dashboardAPI.balanceTimeline(year, scope),
      dashboardAPI.pnlSummary(year, scope),
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
    // Seuil d'alerte tréso basse (Réglages) — non bloquant, 0 = désactivé.
    settingsAPI
      .get()
      .then((s) => setLowAlertThreshold(Number((s as { low_treasury_alert_eur?: string | number }).low_treasury_alert_eur ?? 0)))
      .catch(() => setLowAlertThreshold(0));
  }, [year, scope]);

  // Alerte trésorerie basse : solde courant sous le seuil, ou minimum projeté
  // (mois futurs de la courbe, selon le scope affiché) qui passera dessous.
  const lowAlert = (() => {
    if (!lowAlertThreshold || !balance) return null;
    const current = Number(balance.current_balance_eur ?? 0);
    if (current < lowAlertThreshold) {
      return { kind: 'now' as const, value: current, month: null as string | null };
    }
    let worst: { value: number; month: string } | null = null;
    for (const m of balance.months) {
      if (!m.is_forecast) continue;
      const v = Number(m.balance_eur ?? 0);
      if (v < lowAlertThreshold && (worst === null || v < worst.value)) {
        worst = { value: v, month: m.month };
      }
    }
    return worst ? { kind: 'projected' as const, value: worst.value, month: worst.month } : null;
  })();

  const yearPicker = (
    <div className="flex flex-wrap items-center gap-2">
      {/* Sélecteur de certitude : Réalisé / Engagé / Prévisionnel */}
      <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
        {SCOPES.map((s) => (
          <button
            key={s.value}
            onClick={() => setScope(s.value)}
            className={`border-r border-[var(--border)] px-3 py-1.5 text-sm font-semibold last:border-r-0 ${
              s.value === scope ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--muted)] hover:bg-gray-50'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
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

      <div className={`rounded-xl px-4 py-2 text-xs ${
        scope === 'realized' ? 'bg-emerald-50 text-emerald-800'
        : scope === 'engaged' ? 'bg-blue-50 text-blue-800'
        : 'bg-amber-50 text-amber-800'
      }`}>
        {SCOPE_NOTE[scope]}{' '}
        <span className="opacity-70">Trésorerie, patrimoine, pont et soldes à date restent toujours au réel.</span>
      </div>

      {lowAlert && (
        <div
          className={`rounded-xl border px-4 py-2.5 text-sm ${
            lowAlert.kind === 'now'
              ? 'border-red-200 bg-red-50 text-red-800'
              : 'border-orange-200 bg-orange-50 text-orange-800'
          }`}
        >
          {lowAlert.kind === 'now' ? (
            <>
              🔻 <b>Trésorerie sous le seuil d'alerte</b> — solde actuel {eur(lowAlert.value)} pour
              un seuil de {eur(lowAlertThreshold)} (réglable dans{' '}
              <Link href="/settings" className="font-semibold underline">Réglages</Link>).
            </>
          ) : (
            <>
              ⚠️ <b>Trésorerie projetée sous le seuil</b> — minimum {eur(lowAlert.value)} en{' '}
              {lowAlert.month} pour un seuil de {eur(lowAlertThreshold)} (selon le niveau «{' '}
              {SCOPES.find((s) => s.value === scope)?.label} »).
            </>
          )}
        </div>
      )}

      {Number(invoices?.prior_year_open_count ?? 0) > 0 && (
        <Link
          href="/invoices"
          className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800 hover:bg-red-100"
        >
          <span>
            🚨 <b>{invoices?.prior_year_open_count} facture(s) d'exercice antérieur non rapprochée(s)</b>{' '}
            ({eur(invoices?.prior_year_open_eur)}) — à rapprocher pour éviter un double comptage entre exercices.
          </span>
          <span className="font-semibold">Rapprocher →</span>
        </Link>
      )}

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
        <StatCard label={`Résultat P&L (${SCOPES.find((s) => s.value === scope)?.label.toLowerCase()})`} value={eur(pnl?.result_eur)} tone="pos" />
        <StatCard
          label={scope === 'forecast' ? "IS projeté fin d'exercice" : scope === 'engaged' ? 'IS (engagé)' : 'IS (réalisé à date)'}
          value={eur(pnl?.is_estimate_eur)}
        />
        <StatCard label="Factures en attente" value={eur(invoices?.outstanding_eur)} />
      </div>

      {cashflow && <CashflowChart data={cashflow} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
        {balance && <BalanceChart data={balance} />}
        {pnl && <PnlWidget data={pnl} />}
        {pnl && <DistributionsCard data={pnl} />}
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
