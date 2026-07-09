'use client';

import { useCallback, useEffect, useState } from 'react';
import { transactionsAPI, categoriesAPI, bankingAPI, fxAPI } from '@/api/client';
import { PageTitle, Card, Badge, Empty } from '@/components/ui';
import { eur, money, dateFR } from '@/lib/format';

interface Transaction {
  id: number;
  account_uid: string;
  external_id: string;
  booked_date: string;
  value_date: string;
  amount: string;
  currency: string;
  description: string;
  counterparty: string | null;
  category_id: number | null;
  category_name: string | null;
  kind: string | null;
  fx_rate: string | null;
  amount_eur: string | null;
  linked_conversion_id: number | null;
  invoice_id: number | null;
  created_at: string;
}

interface Category {
  id: number;
  name: string;
  type: string;
  parent_id: number | null;
  is_system: boolean;
}

const KINDS = [
  'revenue',
  'charge',
  'conversion',
  'transfer',
  'investment',
  'other',
] as const;

const KIND_LABELS: Record<string, string> = {
  revenue: 'Revenu',
  charge: 'Charge',
  conversion: 'Conversion',
  transfer: 'Transfert',
  investment: 'Investissement',
  other: 'Autre',
};

function kindTone(kind: string | null): 'neutral' | 'pos' | 'neg' | 'warn' {
  if (kind === 'revenue') return 'pos';
  if (kind === 'charge') return 'neg';
  if (kind === 'conversion' || kind === 'transfer') return 'warn';
  return 'neutral';
}

export default function TransactionsPage() {
  const [rows, setRows] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  // Taux théoriques des Réglages — repli EUR (≈) quand le FX réel n'est pas alloué.
  const [rates, setRates] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [syncMsg, setSyncMsg] = useState<string>('');
  const [syncing, setSyncing] = useState(false);

  // Filtres
  const [categoryFilter, setCategoryFilter] = useState<string>(''); // '' = Toutes, 'uncat', ou id
  const [kindFilter, setKindFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [search, setSearch] = useState<string>(''); // recherche texte (client-side)
  const [checked, setChecked] = useState<Record<number, boolean>>({}); // sélection groupée
  // Vue trésorerie : filtre prédéfini = une ligne du pont « D'où vient ma
  // trésorerie ? » (classement fait côté backend — total liste == ligne du pont).
  const [bridgeFilter, setBridgeFilter] = useState<string>('');
  const [bridgeAsOf, setBridgeAsOf] = useState<string>('');

  // Pré-remplissage depuis l'URL (clic sur une ligne du pont) : ?bridge=&as_of=.
  // as_of assaini : date pure AAAA-MM-JJ uniquement (une datetime est tronquée,
  // une valeur invalide est ignorée) — le backend tolère aussi, double ceinture.
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const b = sp.get('bridge');
    if (b) {
      setBridgeFilter(b);
      const raw = (sp.get('as_of') || '').slice(0, 10);
      setBridgeAsOf(/^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : '');
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string | boolean | undefined> = {
        kind: kindFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        bridge: bridgeFilter || undefined,
        as_of: bridgeFilter ? bridgeAsOf || undefined : undefined,
      };
      if (categoryFilter === 'uncat') {
        params.uncategorized = true;
      } else if (categoryFilter) {
        params.category_id = categoryFilter;
      }
      const data = await transactionsAPI.list(params);
      setRows(data as Transaction[]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, kindFilter, dateFrom, dateTo, bridgeFilter, bridgeAsOf]);

  useEffect(() => {
    categoriesAPI
      .list()
      .then((c) => setCategories(c as Category[]))
      .catch(() => setCategories([]));
    fxAPI
      .list()
      .then((rs) =>
        setRates(
          Object.fromEntries(
            (rs as { currency: string; rate: string | number }[]).map((r) => [
              r.currency,
              Number(r.rate),
            ]),
          ),
        ),
      )
      .catch(() => setRates({}));
  }, []);

  // Année de la vue tréso (suit la date du pont si fournie) + catégories de
  // transferts/placements proposées dans le dropdown (dynamiques, depuis la base).
  const bridgeYear = (bridgeAsOf || new Date().toISOString()).slice(0, 4);
  const treasuryCats = categories.filter((c) =>
    ['transfer', 'internal', 'investment'].includes(c.type),
  );

  // EUR d'une transaction : réel (`amount_eur`, figé par l'allocation FX) sinon
  // montant si déjà en EUR, sinon ≈ natif × taux théorique des Réglages.
  const eurOf = (tx: Transaction): { value: number; approx: boolean } | null => {
    if (tx.amount_eur != null) return { value: Number(tx.amount_eur), approx: false };
    const amt = parseFloat(tx.amount);
    if ((tx.currency || 'EUR').toUpperCase() === 'EUR') return { value: amt, approx: false };
    const rate = rates[(tx.currency || '').toUpperCase()];
    return rate > 0 ? { value: amt * rate, approx: true } : null;
  };

  useEffect(() => {
    load();
  }, [load]);

  const sync = async () => {
    setSyncing(true);
    setSyncMsg('Synchronisation…');
    try {
      const res = await bankingAPI.sync();
      setSyncMsg(
        `✅ ${res.transactions_added ?? 0} ajoutée(s), ${res.transactions_skipped ?? 0} ignorée(s)`,
      );
      await load();
    } catch (e) {
      setSyncMsg(`❌ ${(e as Error).message}`);
    } finally {
      setSyncing(false);
    }
  };

  // Ids cochés (parmi toutes les lignes chargées).
  const selectedIds = Object.entries(checked)
    .filter(([, v]) => v)
    .map(([k]) => Number(k));

  const updateCategory = async (tx: Transaction, value: string) => {
    const category_id = value === '' ? null : Number(value);
    // Option B : si la ligne éditée est cochée, on applique la catégorie à
    // TOUTES les lignes cochées d'un coup ; sinon uniquement à cette ligne.
    const targetIds = checked[tx.id] && selectedIds.length > 0 ? selectedIds : [tx.id];
    try {
      const updated = (await transactionsAPI.bulkCategorize(
        targetIds,
        category_id,
      )) as Transaction[];
      const byId = new Map(updated.map((u) => [u.id, u]));
      setRows((prev) => prev.map((r) => byId.get(r.id) ?? r));
      if (targetIds.length > 1) {
        setChecked({}); // on vide la sélection après une application groupée
        setSyncMsg(`✅ Catégorie appliquée à ${targetIds.length} transactions`);
      }
    } catch (e) {
      setSyncMsg(`❌ ${(e as Error).message}`);
    }
  };

  const toggleOne = (id: number) =>
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));

  const selectCls =
    'rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]';

  // Recherche texte sur description + contrepartie + montant (insensible à la
  // casse ; le montant matche en notation point OU virgule : « 386.17 » / « 386,17 »).
  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter(
        (t) =>
          (t.description ?? '').toLowerCase().includes(q) ||
          (t.counterparty ?? '').toLowerCase().includes(q) ||
          (t.amount ?? '').includes(q.replace(',', '.')) ||
          (t.amount ?? '').replace('.', ',').includes(q),
      )
    : rows;

  const allChecked = filtered.length > 0 && filtered.every((t) => checked[t.id]);
  const toggleAll = () => {
    if (allChecked) {
      setChecked({});
    } else {
      setChecked(Object.fromEntries(filtered.map((t) => [t.id, true])));
    }
  };
  const selectedCount = selectedIds.length;

  return (
    <div>
      <PageTitle
        title="Transactions"
        subtitle={`${filtered.length} opération(s)${q ? ` sur ${rows.length}` : ''}${
          selectedCount > 0 ? ` · ${selectedCount} sélectionnée(s) — change la catégorie d'une ligne cochée pour l'appliquer à toutes` : ''
        }`}
        action={
          <button
            onClick={sync}
            disabled={syncing}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {syncing ? 'Synchronisation…' : 'Synchroniser'}
          </button>
        }
      />

      {syncMsg && <p className="mb-4 text-sm text-[var(--muted)]">{syncMsg}</p>}

      {/* Filtres */}
      <Card className="mb-5">
        <label className="mb-3 flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">Recherche</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Description ou contrepartie…"
            aria-label="Rechercher une transaction"
            className={selectCls}
          />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Vue tréso</span>
            <select
              value={bridgeFilter}
              onChange={(e) => setBridgeFilter(e.target.value)}
              aria-label="Vue trésorerie"
              className={selectCls}
            >
              <option value="">— (tout)</option>
              <option value="received_current">Encaissé — factures {bridgeYear}</option>
              <option value="received_prior">Encaissé — factures &lt; {bridgeYear}</option>
              <option value="other_revenue">Autres revenus (non facturés)</option>
              <option value="charges">Charges (nettes)</option>
              {treasuryCats.map((c) => (
                <option key={c.id} value={`cat:${c.name}`}>
                  {c.name}
                </option>
              ))}
              <option value="residual">Écarts FX (conversions)</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Catégorie</span>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className={selectCls}
            >
              <option value="">Toutes</option>
              <option value="uncat">À catégoriser</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Type</span>
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
              className={selectCls}
            >
              <option value="">Tous</option>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Du</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className={selectCls}
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Au</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className={selectCls}
            />
          </label>
        </div>
      </Card>

      {/* Table */}
      {error ? (
        <Empty>❌ Erreur : {error}</Empty>
      ) : loading ? (
        <Empty>Chargement…</Empty>
      ) : filtered.length === 0 ? (
        <Empty>{q ? 'Aucune transaction ne correspond à la recherche.' : 'Aucune transaction.'}</Empty>
      ) : (
        <Card className="overflow-x-auto p-0">
          {/* Densité « Excel » : rangées fines, texte 13px, description sur une ligne. */}
          <table className="w-full text-[13px] leading-tight">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                <th className="px-3 py-1 font-medium">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    onChange={toggleAll}
                    aria-label="Tout sélectionner"
                    title="Tout sélectionner (lignes affichées)"
                  />
                </th>
                <th className="px-3 py-1 font-medium">Date</th>
                <th className="px-3 py-1 font-medium">Description</th>
                <th className="px-3 py-1 font-medium">Type</th>
                <th className="px-3 py-1 font-medium">Catégorie</th>
                <th className="px-3 py-1 text-right font-medium">Montant (devise)</th>
                <th className="px-3 py-1 text-right font-medium">Montant (EUR)</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((tx) => {
                const amt = parseFloat(tx.amount);
                const uncategorized = tx.category_id == null;
                return (
                  <tr
                    key={tx.id}
                    className={`border-b border-[var(--border)] last:border-0 hover:bg-black/[0.02] ${
                      checked[tx.id] ? 'bg-[var(--accent)]/5' : ''
                    }`}
                  >
                    <td className="px-3 py-1">
                      <input
                        type="checkbox"
                        checked={!!checked[tx.id]}
                        onChange={() => toggleOne(tx.id)}
                        aria-label={`Sélectionner ${tx.description || tx.id}`}
                      />
                    </td>
                    <td className="whitespace-nowrap px-3 py-1 text-[var(--muted)]">
                      {dateFR(tx.booked_date)}
                    </td>
                    <td className="max-w-[320px] px-3 py-1">
                      {/* Une seule ligne (tronquée) — contrepartie inline, détail au survol. */}
                      <div
                        className="truncate"
                        title={[tx.description, tx.counterparty].filter(Boolean).join(' — ')}
                      >
                        <span className="font-medium">{tx.description || '—'}</span>
                        {tx.counterparty && (
                          <span className="ml-1.5 text-xs text-[var(--muted)]">
                            {tx.counterparty}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-1">
                      {tx.kind ? (
                        <Badge tone={kindTone(tx.kind)}>
                          {KIND_LABELS[tx.kind] ?? tx.kind}
                        </Badge>
                      ) : (
                        <span className="text-[var(--muted)]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-1">
                      <select
                        value={tx.category_id ?? ''}
                        onChange={(e) => updateCategory(tx, e.target.value)}
                        aria-label={`Catégorie de ${tx.description || tx.id}`}
                        className={`rounded-md border px-1.5 py-0.5 text-xs outline-none focus:border-[var(--accent)] ${
                          uncategorized
                            ? 'border-amber-300 bg-amber-50 text-amber-800'
                            : 'border-[var(--border)] bg-[var(--panel)]'
                        }`}
                      >
                        <option value="">À catégoriser</option>
                        {categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td
                      className="whitespace-nowrap px-3 py-1 text-right font-medium tabular-nums"
                      style={{
                        color: amt < 0 ? 'var(--neg)' : amt > 0 ? 'var(--pos)' : undefined,
                      }}
                    >
                      {money(tx.amount, tx.currency)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1 text-right tabular-nums text-[var(--muted)]">
                      {(() => {
                        const e = eurOf(tx);
                        if (e == null) return '—';
                        // ≈ = converti au taux théorique (pas encore de FX réel alloué).
                        return `${e.approx ? '≈ ' : ''}${eur(e.value)}`;
                      })()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              {/* Total EUR des lignes AFFICHÉES — suit recherche + filtres. */}
              <tr className="border-t-2 border-[var(--border)] bg-gray-50/60 font-semibold">
                <td colSpan={6} className="px-3 py-1.5 text-right">
                  Total ({filtered.length} ligne{filtered.length > 1 ? 's' : ''} affichées)
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                  {(() => {
                    let total = 0;
                    let approx = false;
                    for (const tx of filtered) {
                      const e = eurOf(tx);
                      if (e == null) continue;
                      total += e.value;
                      if (e.approx) approx = true;
                    }
                    return `${approx ? '≈ ' : ''}${eur(total)}`;
                  })()}
                </td>
              </tr>
            </tfoot>
          </table>
        </Card>
      )}
    </div>
  );
}
