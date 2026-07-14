'use client';

import { useEffect, useState } from 'react';
import { investmentsAPI, fxAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { money, eur, dateFR } from '@/lib/format';

type Investment = {
  id: number;
  label: string;
  type: string;
  currency: string;
  opening_value: string | number;
  opening_value_eur: string | number;
  current_value: string | number;
  current_value_eur: string | number;
  as_of_date: string | null;
  note: string;
  expected_value: string | number | null;
  expected_value_eur: string | number | null;
  expected_month: string | null;
  opening_transaction_id: number | null;
  closed_date: string | null;
  closed_transaction_id: number | null;
  realized_gain_eur: string | number | null;
};

type Candidate = {
  id: number;
  booked_date: string | null;
  description: string;
  counterparty: string;
  amount: string;
  currency: string;
  amount_eur: string;
};

type Summary = {
  total_opening_value_eur: string;
  total_current_value_eur: string;
  gain_eur: string;
};

const TYPES = ['crypto', 'bourse', 'placement', 'autre'];
const CURRENCIES = ['EUR', 'USD', 'GBP', 'CAD', 'CHF'];

const EMPTY = {
  label: '', type: 'crypto', currency: 'EUR',
  opening_value: '', current_value: '', as_of_date: '', note: '',
  expected_value: '', expected_month: '',
};

const typeTone: Record<string, 'neutral' | 'pos' | 'warn'> = {
  crypto: 'warn', bourse: 'pos', placement: 'neutral', autre: 'neutral',
};

export default function PlacementsPage() {
  const [rows, setRows] = useState<Investment[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [fxRates, setFxRates] = useState<Record<string, number>>({ EUR: 1 });
  const [form, setForm] = useState<Record<string, string>>({ ...EMPTY });
  const [editId, setEditId] = useState<number | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  async function load() {
    try {
      const [list, sum] = await Promise.all([
        investmentsAPI.list(),
        investmentsAPI.summary(),
      ]);
      setRows(list as Investment[]);
      setSummary(sum as Summary);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    fxAPI
      .list()
      .then((rs) => {
        const map: Record<string, number> = { EUR: 1 };
        (rs as { currency: string; rate: string | number }[]).forEach(
          (r) => (map[r.currency] = Number(r.rate)),
        );
        setFxRates(map);
      })
      .catch(() => undefined);
  }, []);

  const rate = (cur: string) => (cur === 'EUR' ? 1 : fxRates[cur] ?? 1);

  function newInvestment() {
    setForm({ ...EMPTY });
    setEditId(null);
    setStatus('');
  }

  function editInvestment(inv: Investment) {
    setForm({
      label: inv.label, type: inv.type, currency: inv.currency,
      opening_value: String(inv.opening_value), current_value: String(inv.current_value),
      as_of_date: inv.as_of_date ?? '', note: inv.note ?? '',
      expected_value: inv.expected_value != null ? String(inv.expected_value) : '',
      expected_month: inv.expected_month ?? '',
    });
    setEditId(inv.id);
    setStatus('');
  }

  async function save() {
    if (!form.label.trim()) {
      setStatus('❌ Le libellé est obligatoire');
      return;
    }
    setStatus('Enregistrement…');
    const r = rate(form.currency);
    const opening = Number(form.opening_value) || 0;
    const current = Number(form.current_value) || 0;
    const payload = {
      label: form.label,
      type: form.type,
      currency: form.currency,
      opening_value: opening,
      current_value: current,
      // EUR dérivé du taux de change courant (Réglages).
      opening_value_eur: opening * r,
      current_value_eur: current * r,
      as_of_date: form.as_of_date || null,
      note: form.note,
      // Remboursement attendu (produit à échéance) — vide = aucun.
      expected_value: form.expected_value ? Number(form.expected_value) : null,
      expected_value_eur: form.expected_value ? Number(form.expected_value) * r : null,
      expected_month: form.expected_month || null,
    };
    try {
      if (editId) {
        await investmentsAPI.update(editId, payload);
      } else {
        await investmentsAPI.create(payload);
      }
      setStatus('✅ Enregistré');
      newInvestment();
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function remove(inv: Investment) {
    if (!confirm(`Supprimer le placement « ${inv.label} » ?`)) return;
    try {
      await investmentsAPI.remove(inv.id);
      if (editId === inv.id) newInvestment();
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  // Rapprochement du remboursement : placement en cours + encaissements candidats.
  const [reconciling, setReconciling] = useState<Investment | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [recMsg, setRecMsg] = useState('');

  async function openReconcile(inv: Investment) {
    setRecMsg('');
    try {
      setCandidates((await investmentsAPI.candidates(inv.id)) as Candidate[]);
      setReconciling(inv);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function doReconcile(txId: number) {
    if (!reconciling) return;
    setRecMsg('…');
    try {
      await investmentsAPI.reconcile(reconciling.id, txId);
      setReconciling(null);
      load();
    } catch (e) {
      setRecMsg(`❌ ${(e as Error).message}`);
    }
  }

  async function unreconcile(inv: Investment) {
    if (!confirm(`Annuler la clôture de « ${inv.label} » ?`)) return;
    try {
      await investmentsAPI.unreconcile(inv.id);
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  // Rapprochement de l'ACHAT : placement + transactions sortantes candidates.
  const [linkingBuy, setLinkingBuy] = useState<Investment | null>(null);
  const [buyCandidates, setBuyCandidates] = useState<Candidate[]>([]);
  const [buyMsg, setBuyMsg] = useState('');

  async function openLinkPurchase(inv: Investment) {
    setBuyMsg('');
    try {
      setBuyCandidates((await investmentsAPI.purchaseCandidates(inv.id)) as Candidate[]);
      setLinkingBuy(inv);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function doLinkPurchase(txId: number) {
    if (!linkingBuy) return;
    setBuyMsg('…');
    try {
      await investmentsAPI.linkPurchase(linkingBuy.id, txId);
      setLinkingBuy(null);
      load();
    } catch (e) {
      setBuyMsg(`❌ ${(e as Error).message}`);
    }
  }

  async function unlinkPurchase(inv: Investment) {
    if (!confirm(`Délier l'achat de « ${inv.label} » ?`)) return;
    try {
      await investmentsAPI.unlinkPurchase(inv.id);
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  const gain = Number(summary?.gain_eur ?? 0);

  return (
    <div>
      <PageTitle
        title="Placements"
        subtitle="Suivi manuel crypto / bourse — gains attendus et réalisés au P&L + IS, le latent reste hors base"
      />
      {error && <p className="mb-4 text-sm text-[var(--neg)]">❌ {error}</p>}

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Valeur d'ouverture" value={eur(summary?.total_opening_value_eur ?? 0)} />
        <StatCard label="Valeur actuelle" value={eur(summary?.total_current_value_eur ?? 0)} />
        <StatCard
          label="Plus-value latente"
          value={`${gain >= 0 ? '+' : ''}${eur(gain)}`}
          tone={gain >= 0 ? 'pos' : 'neg'}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
        {/* Liste */}
        <Card>
          <div className="mb-3 text-sm font-semibold">Mes placements ({rows.length})</div>
          {rows.length === 0 ? (
            <Empty>Aucun placement. Ajoute-en un via le formulaire.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted)]">
                    <th className="py-2 pr-2 text-left font-semibold">Placement</th>
                    <th className="px-2 py-2 text-left font-semibold">Type</th>
                    <th className="px-2 py-2 text-right font-semibold">Devise</th>
                    <th className="px-2 py-2 text-right font-semibold">Investi (achat) 🔗</th>
                    <th className="px-2 py-2 text-right font-semibold">Actuelle</th>
                    <th className="px-2 py-2 text-right font-semibold">+/- (€)</th>
                    <th className="px-2 py-2 text-right font-semibold">Remb. attendu</th>
                    <th className="px-2 py-2 text-right font-semibold">Échéance</th>
                    <th className="px-2 py-2 text-right font-semibold">Au</th>
                    <th className="py-2 pl-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((inv) => {
                    const g = Number(inv.current_value_eur) - Number(inv.opening_value_eur);
                    return (
                      <tr key={inv.id} className="border-b border-gray-100">
                        <td className="py-2 pr-2 text-left font-medium">{inv.label}</td>
                        <td className="px-2 py-2 text-left">
                          <Badge tone={typeTone[inv.type] ?? 'neutral'}>{inv.type}</Badge>
                        </td>
                        <td className="px-2 py-2 text-right text-[var(--muted)]">{inv.currency}</td>
                        <td className="px-2 py-2 text-right">
                          {money(inv.opening_value, inv.currency)}
                          <div className="mt-1">
                            {inv.opening_transaction_id ? (
                              <span
                                className="inline-flex items-center gap-1 rounded-full border border-[var(--accent)] bg-blue-50 px-2 py-0.5 text-[10px] text-[var(--accent)]"
                                title="Investi ancré sur la sortie bancaire réelle"
                              >
                                🔗 tx#{inv.opening_transaction_id}
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700"
                                title="Montant saisi manuellement — non rapproché à une transaction"
                              >
                                ⚠ saisie manuelle
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2 text-right">{money(inv.current_value, inv.currency)}</td>
                        <td className={`px-2 py-2 text-right font-semibold ${g >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
                          {inv.closed_date ? (
                            <span title={`Clôturé le ${dateFR(inv.closed_date)} — gain réalisé`}>
                              {Number(inv.realized_gain_eur) >= 0 ? '+' : ''}{eur(inv.realized_gain_eur ?? 0)} ✓
                            </span>
                          ) : (
                            <>{g >= 0 ? '+' : ''}{eur(g)}</>
                          )}
                        </td>
                        <td className="px-2 py-2 text-right">
                          {inv.expected_value != null ? money(inv.expected_value, inv.currency) : <span className="text-[var(--muted)]">—</span>}
                        </td>
                        <td className="px-2 py-2 text-right text-[var(--muted)]">{inv.expected_month ?? '—'}</td>
                        <td className="px-2 py-2 text-right text-[var(--muted)]">{inv.as_of_date ? dateFR(inv.as_of_date) : '—'}</td>
                        <td className="py-2 pl-2 text-right whitespace-nowrap">
                          {inv.closed_date ? (
                            <button
                              onClick={() => unreconcile(inv)}
                              className="rounded-lg border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--neg)] hover:bg-red-50"
                              title={`Clôturé le ${dateFR(inv.closed_date)} — annuler le rapprochement`}
                            >
                              Annuler rappr.
                            </button>
                          ) : (
                            <button
                              onClick={() => openReconcile(inv)}
                              className="rounded-lg border border-[var(--accent)] px-2 py-0.5 text-xs text-[var(--accent)] hover:bg-blue-50"
                              title="Rapprocher le remboursement à un encaissement réel (gain réalisé → P&L + IS)"
                            >
                              Rapprocher
                            </button>
                          )}{' '}
                          {inv.opening_transaction_id ? (
                            <button
                              onClick={() => unlinkPurchase(inv)}
                              className="rounded-lg border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)] hover:bg-gray-50"
                              title={`Achat lié à tx#${inv.opening_transaction_id} — délier`}
                            >
                              Délier achat
                            </button>
                          ) : (
                            <button
                              onClick={() => openLinkPurchase(inv)}
                              className="rounded-lg border border-[var(--accent)] px-2 py-0.5 text-xs text-[var(--accent)] hover:bg-blue-50"
                              title="Rapprocher l'achat à la sortie bancaire qui l'a financé (fige l'investi réel)"
                            >
                              🔗 Rapprocher l&apos;achat
                            </button>
                          )}{' '}
                          <button onClick={() => editInvestment(inv)} className="text-[var(--muted)] hover:text-[var(--accent)]" title="Éditer">✏️</button>{' '}
                          <button onClick={() => remove(inv)} className="text-[var(--muted)] hover:text-[var(--neg)]" title="Supprimer">🗑️</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-xs text-[var(--muted)]">
            💡 Le gain <b>latent</b> reste hors P&L et hors IS. Comptent : le <b>remboursement
            attendu</b> (scope prévisionnel — gain attendu au P&L, cash à l'échéance dans la
            courbe) et le <b>réalisé</b> au rapprochement (gain = encaissé − investi, une perte
            réalisée est déductible). Traitement fiscal fin : ton expert-comptable.
          </p>
        </Card>

        {/* Formulaire */}
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">{editId ? 'Modifier le placement' : 'Nouveau placement'}</div>
            {editId && (
              <button onClick={newInvestment} className="text-xs text-[var(--accent)]">+ Nouveau</button>
            )}
          </div>
          {status && <p className="mb-3 text-sm text-[var(--muted)]">{status}</p>}

          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Libellé</span>
              <input value={form.label} placeholder="Bitcoin (Kraken)"
                onChange={(e) => setForm((p) => ({ ...p, label: e.target.value }))}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Type</span>
                <select value={form.type} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 outline-none focus:border-[var(--accent)]">
                  {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Devise</span>
                <select value={form.currency} onChange={(e) => setForm((p) => ({ ...p, currency: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 outline-none focus:border-[var(--accent)]">
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Valeur d'ouverture</span>
                <input type="number" step="any" value={form.opening_value} placeholder="10000"
                  onChange={(e) => setForm((p) => ({ ...p, opening_value: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-right outline-none focus:border-[var(--accent)]" />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Valeur actuelle</span>
                <input type="number" step="any" value={form.current_value} placeholder="13000"
                  onChange={(e) => setForm((p) => ({ ...p, current_value: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-right outline-none focus:border-[var(--accent)]" />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Date de valorisation</span>
              <input type="date" value={form.as_of_date}
                onChange={(e) => setForm((p) => ({ ...p, as_of_date: e.target.value }))}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Remb. attendu ({form.currency})</span>
                <input type="number" step="any" value={form.expected_value} placeholder="optionnel"
                  onChange={(e) => setForm((p) => ({ ...p, expected_value: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-right outline-none focus:border-[var(--accent)]" />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">Échéance attendue</span>
                <input type="month" value={form.expected_month}
                  onChange={(e) => setForm((p) => ({ ...p, expected_month: e.target.value }))}
                  className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]" />
              </label>
            </div>
            <p className="-mt-1 text-xs text-[var(--muted)]">
              Optionnel — produit à échéance : le gain attendu entre au P&L prévisionnel
              (et à l'IS projeté), le cash à l'échéance dans la courbe de trésorerie.
            </p>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Note</span>
              <input value={form.note} placeholder="optionnel"
                onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]" />
            </label>
            <button onClick={save} className="mt-1 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90">
              Enregistrer
            </button>
            {form.currency !== 'EUR' && (
              <p className="text-xs text-[var(--muted)]">
                Valeur EUR calculée au taux {form.currency} des Réglages (1 {form.currency} = {rate(form.currency)} €).
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Rapprochement : choisir l'encaissement réel du remboursement. */}
      {reconciling && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl bg-[var(--panel)] p-5 shadow-xl">
            <div className="mb-1 text-sm font-semibold">
              Rapprocher « {reconciling.label} » à un encaissement
            </div>
            <p className="mb-3 text-xs text-[var(--muted)]">
              Investi : <b>{eur(reconciling.opening_value_eur)}</b>
              {reconciling.expected_value_eur != null && (
                <> · remboursement attendu : {eur(reconciling.expected_value_eur)}
                  {reconciling.expected_month ? ` (${reconciling.expected_month})` : ''}</>
              )}
              . Gain réalisé = encaissé − investi → P&L + base IS ; la transaction passe en flux interne.
            </p>
            {candidates.length === 0 ? (
              <Empty>Aucun encaissement candidat (transactions positives sans facture liée).</Empty>
            ) : (
              <div className="max-h-72 overflow-y-auto rounded-lg border border-[var(--border)]">
                {candidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => doReconcile(c.id)}
                    className="flex w-full items-center justify-between border-b border-[var(--border)] px-3 py-2 text-left text-sm last:border-b-0 hover:bg-blue-50"
                  >
                    <span className="truncate">
                      <span className="text-[var(--muted)]">{c.booked_date ? dateFR(c.booked_date) : '—'}</span>{' '}
                      {c.description || c.counterparty}
                    </span>
                    <span className="ml-2 shrink-0 tabular-nums">
                      {money(c.amount, c.currency)}
                      <span className="ml-1.5 text-xs text-[var(--pos)]">
                        → gain {(() => { const gv = Number(c.amount_eur) - Number(reconciling.opening_value_eur); return `${gv >= 0 ? '+' : ''}${eur(gv)}`; })()}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            {recMsg && <p className="mt-2 text-xs">{recMsg}</p>}
            <div className="mt-3 text-right">
              <button
                onClick={() => setReconciling(null)}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent)]"
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rapprochement de l'ACHAT : choisir la sortie bancaire qui a financé le placement. */}
      {linkingBuy && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl bg-[var(--panel)] p-5 shadow-xl">
            <div className="mb-1 text-sm font-semibold">
              Rapprocher l&apos;achat de « {linkingBuy.label} »
            </div>
            <p className="mb-3 text-xs text-[var(--muted)]">
              Investi actuel : <b>{money(linkingBuy.opening_value, linkingBuy.currency)}</b>. Choisis
              la transaction <b>sortante</b> qui l&apos;a financé — l&apos;investi sera recalé sur le
              montant réellement sorti (natif exact), et la ligne passe en flux interne (jamais comptée
              en charge).
            </p>
            {buyCandidates.length === 0 ? (
              <Empty>Aucune sortie candidate (transactions négatives non déjà liées à un placement).</Empty>
            ) : (
              <div className="max-h-72 overflow-y-auto rounded-lg border border-[var(--border)]">
                {buyCandidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => doLinkPurchase(c.id)}
                    className="flex w-full items-center justify-between border-b border-[var(--border)] px-3 py-2 text-left text-sm last:border-b-0 hover:bg-blue-50"
                  >
                    <span className="truncate">
                      <span className="text-[var(--muted)]">{c.booked_date ? dateFR(c.booked_date) : '—'}</span>{' '}
                      {c.description || c.counterparty}
                    </span>
                    <span className="ml-2 shrink-0 tabular-nums text-[var(--neg)]">
                      {money(c.amount, c.currency)}
                      <span className="ml-1.5 text-xs text-[var(--muted)]">≈ {eur(c.amount_eur)}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            {buyMsg && <p className="mt-2 text-xs">{buyMsg}</p>}
            <div className="mt-3 text-right">
              <button
                onClick={() => setLinkingBuy(null)}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent)]"
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
