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

  const gain = Number(summary?.gain_eur ?? 0);

  return (
    <div>
      <PageTitle
        title="Placements"
        subtitle="Suivi manuel crypto / bourse — les plus-values latentes alimentent l'estimation d'IS"
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
                    <th className="px-2 py-2 text-right font-semibold">Ouverture</th>
                    <th className="px-2 py-2 text-right font-semibold">Actuelle</th>
                    <th className="px-2 py-2 text-right font-semibold">+/- (€)</th>
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
                        <td className="px-2 py-2 text-right">{money(inv.opening_value, inv.currency)}</td>
                        <td className="px-2 py-2 text-right">{money(inv.current_value, inv.currency)}</td>
                        <td className={`px-2 py-2 text-right font-semibold ${g >= 0 ? 'text-[var(--pos)]' : 'text-[var(--neg)]'}`}>
                          {g >= 0 ? '+' : ''}{eur(g)}
                        </td>
                        <td className="px-2 py-2 text-right text-[var(--muted)]">{inv.as_of_date ? dateFR(inv.as_of_date) : '—'}</td>
                        <td className="py-2 pl-2 text-right whitespace-nowrap">
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
            💡 Seules les plus-values <b>positives</b> (valeur actuelle &gt; ouverture) entrent dans la base imposable de l'IS estimé.
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
    </div>
  );
}
