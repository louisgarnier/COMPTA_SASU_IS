'use client';

import { useEffect, useState } from 'react';
import { fxAPI } from '@/api/client';
import { Card, Badge } from '@/components/ui';

type Rate = { currency: string; rate: string | number; missing: boolean };

export function FxRatesCard() {
  const [rows, setRows] = useState<Rate[]>([]);
  const [status, setStatus] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [newCur, setNewCur] = useState('');
  const [newRate, setNewRate] = useState('');

  const load = () =>
    fxAPI
      .list()
      .then((r) => {
        setRows(r);
        setLoaded(true);
      })
      .catch((e) => setStatus(`❌ ${(e as Error).message}`));

  useEffect(() => {
    load();
  }, []);

  const setRate = (cur: string, val: string) =>
    setRows((rs) => rs.map((r) => (r.currency === cur ? { ...r, rate: val } : r)));

  const save = async () => {
    setStatus('Enregistrement…');
    try {
      const updated = await fxAPI.save(
        rows.map((r) => ({ currency: r.currency, rate: r.rate })),
      );
      setRows(updated);
      setStatus('✅ Enregistré');
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  };

  const addCurrency = async () => {
    const cur = newCur.trim().toUpperCase();
    if (cur.length !== 3) {
      setStatus('❌ Code devise à 3 lettres (ex. GBP)');
      return;
    }
    if (cur === 'EUR' || rows.some((r) => r.currency === cur)) {
      setStatus(`❌ ${cur} est déjà dans la liste`);
      return;
    }
    const rate = Number(newRate);
    if (!(rate > 0)) {
      setStatus('❌ Le taux doit être supérieur à 0');
      return;
    }
    setStatus('Ajout…');
    try {
      const updated = await fxAPI.save([
        ...rows.map((r) => ({ currency: r.currency, rate: r.rate })),
        { currency: cur, rate: newRate },
      ]);
      setRows(updated);
      setNewCur('');
      setNewRate('');
      setStatus(`✅ ${cur} ajouté`);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  };

  const missing = rows.some((r) => r.missing);

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between">
        <div className="text-sm font-semibold">Taux de change (FX → EUR)</div>
        {rows.length > 0 && (
          <button
            onClick={save}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
          >
            Enregistrer les taux
          </button>
        )}
      </div>
      <p className="mb-3 text-xs text-[var(--muted)]">
        Taux théorique appliqué pour convertir chaque devise en EUR (total tréso,
        P&amp;L, IS). EUR = 1. Les devises listées sont celles présentes dans tes
        transactions et comptes.
      </p>

      {missing && (
        <p className="mb-3 text-sm text-amber-700">
          ⚠️ Une ou plusieurs devises sont sans taux — renseigne-les pour une
          conversion correcte.
        </p>
      )}

      {!loaded ? (
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">
          Aucune devise étrangère détectée (tout est en EUR).
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-[var(--border)]">
          <div className="flex items-center justify-between py-2 text-sm">
            <span className="font-medium">EUR</span>
            <span className="tabular text-[var(--muted)]">1 (référence)</span>
          </div>
          {rows.map((r) => (
            <div key={r.currency} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="flex items-center gap-2 font-medium">
                1 {r.currency}
                {r.missing && <Badge tone="warn">à renseigner</Badge>}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[var(--muted)]">=</span>
                <input
                  type="number"
                  step="any"
                  value={String(r.rate ?? '')}
                  onChange={(e) => setRate(r.currency, e.target.value)}
                  className="w-28 rounded-lg border border-[var(--border)] px-2 py-1 text-right tabular outline-none focus:border-[var(--accent)]"
                />
                <span className="text-[var(--muted)]">€</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {loaded && (
        <div className="mt-3 flex items-end gap-2 border-t border-[var(--border)] pt-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            Devise
            <input
              value={newCur}
              onChange={(e) => setNewCur(e.target.value.toUpperCase())}
              placeholder="GBP"
              maxLength={3}
              className="w-20 rounded-lg border border-[var(--border)] px-2 py-1 text-sm uppercase outline-none focus:border-[var(--accent)]"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            Taux → EUR
            <input
              type="number"
              step="any"
              value={newRate}
              onChange={(e) => setNewRate(e.target.value)}
              placeholder="1.17"
              className="w-28 rounded-lg border border-[var(--border)] px-2 py-1 text-right text-sm tabular outline-none focus:border-[var(--accent)]"
            />
          </label>
          <button
            onClick={addCurrency}
            className="rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)] hover:bg-[var(--accent)]/10"
          >
            + Ajouter une devise
          </button>
        </div>
      )}

      {status && <p className="mt-3 text-sm text-[var(--muted)]">{status}</p>}
    </Card>
  );
}
