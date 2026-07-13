'use client';

import { useEffect, useState } from 'react';
import { openingsAPI, type OpeningsView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { eur, money } from '@/lib/format';

/**
 * Réglages → Soldes d'ouverture d'exercice.
 *
 * Le solde de chaque compte au 31/12 (repris du relevé) ancre la reconstruction
 * de trésorerie de l'exercice suivant. Aucune valeur en dur : tout est saisi ici
 * et vit en base. La colonne « Contrôle » compare la saisie à l'ouverture
 * implicite (solde actuel − mouvements) pour repérer un flux manquant.
 */
export function OpeningBalancesCard() {
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [view, setView] = useState<OpeningsView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [newYearInput, setNewYearInput] = useState('');

  // Charge la liste des exercices puis sélectionne l'exercice courant (max).
  useEffect(() => {
    openingsAPI
      .years()
      .then((r) => {
        setYears(r.years);
        setYear(r.years.length ? r.years[r.years.length - 1] : new Date().getFullYear());
      })
      .catch((e) => setStatus(`❌ ${(e as Error).message}`));
  }, []);

  // Pré-remplit le champ « nouvel exercice » avec l'année passée manquante la
  // plus récente (min − 1) dès que la liste des exercices est connue — ex.
  // import d'un historique 2025 alors que seul 2026 existe déjà.
  useEffect(() => {
    if (years.length) setNewYearInput(String(Math.min(...years) - 1));
  }, [years]);

  useEffect(() => {
    if (year == null) return;
    setLoading(true);
    openingsAPI
      .get(year)
      .then((v) => {
        setView(v);
        setEdits(
          Object.fromEntries(
            v.accounts.map((a) => [a.account_uid, a.balance ?? '']),
          ),
        );
      })
      .catch((e) => setStatus(`❌ ${(e as Error).message}`))
      .finally(() => setLoading(false));
  }, [year]);

  // Ajoute n'importe quel exercice (passé OU futur) saisi dans le champ dédié
  // — nécessaire pour renseigner l'ouverture d'un historique importé
  // après coup (ex. import CSV 2025 alors que 2026 est déjà en place).
  const addYear = () => {
    const y = parseInt(newYearInput, 10);
    if (!Number.isFinite(y) || y < 1000 || y > 9999) {
      setStatus('❌ Année invalide');
      return;
    }
    if (!years.includes(y)) setYears([...years, y].sort((a, b) => a - b));
    setYear(y);
    setStatus('');
  };

  const save = async () => {
    if (year == null) return;
    setStatus('Enregistrement…');
    try {
      const items = Object.entries(edits)
        .filter(([, v]) => v !== '' && v != null)
        .map(([account_uid, balance]) => ({ account_uid, balance: String(balance) }));
      const updated = await openingsAPI.save(year, items);
      setView(updated);
      setEdits(
        Object.fromEntries(updated.accounts.map((a) => [a.account_uid, a.balance ?? ''])),
      );
      if (!years.includes(year)) setYears([...years, year].sort((a, b) => a - b));
      setStatus(`✅ Ouvertures ${year} enregistrées`);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  };

  const closingYear = year != null ? year - 1 : null;

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">Soldes d'ouverture d'exercice</div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[var(--muted)]">Exercice</span>
          <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
            {years.map((y) => (
              <button
                key={y}
                onClick={() => setYear(y)}
                className={`border-r border-[var(--border)] px-2.5 py-1 text-xs font-medium last:border-r-0 ${
                  y === year ? 'bg-[var(--accent)] text-white' : 'text-[var(--muted)] hover:bg-gray-50'
                }`}
              >
                {y}
              </button>
            ))}
            <input
              type="number"
              aria-label="Nouvel exercice à ajouter"
              value={newYearInput}
              onChange={(e) => setNewYearInput(e.target.value)}
              className="w-16 border-l border-[var(--border)] px-1.5 py-1 text-center text-xs tabular outline-none focus:border-[var(--accent)]"
            />
            <button
              onClick={addYear}
              className="border-l border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--accent)] hover:bg-gray-50"
            >
              + ajouter
            </button>
          </div>
        </div>
      </div>

      <p className="mb-3 text-xs text-[var(--muted)]">
        Saisis le solde de chaque compte{' '}
        <b>au 31/12/{closingYear ?? '—'}</b> (depuis tes relevés Revolut &amp; Qonto).
        Ces montants deviennent le point de départ {year}. La colonne « Contrôle »
        compare ta saisie à la reconstruction <i>solde actuel − mouvements de l'exercice</i>.
      </p>

      {loading || !view ? (
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular">
              <thead>
                <tr className="text-left text-xs uppercase text-[var(--muted)]">
                  <th className="py-2 pr-3 font-medium">Compte</th>
                  <th className="py-2 pr-3 font-medium">Devise</th>
                  <th className="py-2 pr-3 text-right font-medium">Solde au 31/12/{closingYear}</th>
                  <th className="py-2 pl-3 font-medium">Contrôle (vs mouvements)</th>
                </tr>
              </thead>
              <tbody>
                {view.accounts.map((a) => (
                  <tr key={a.account_uid} className="border-t border-[var(--border)]">
                    <td className="py-2 pr-3">
                      <div className="font-medium">{a.name || a.provider}</div>
                      <div className="text-[11px] text-[var(--muted)]">
                        …{a.account_uid.slice(-8)}
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tone="neutral">{a.currency}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <input
                        type="number"
                        step="any"
                        aria-label={`Solde ${a.name || a.account_uid}`}
                        value={edits[a.account_uid] ?? ''}
                        onChange={(e) =>
                          setEdits({ ...edits, [a.account_uid]: e.target.value })
                        }
                        className="w-32 rounded-lg border border-[var(--border)] px-2 py-1 text-right tabular outline-none focus:border-[var(--accent)]"
                      />
                    </td>
                    <td className="py-2 pl-3">
                      {a.control == null ? (
                        <span className="text-xs text-[var(--muted)]">— saisir pour contrôler</span>
                      ) : a.control.status === 'ok' ? (
                        <span className="text-xs font-semibold text-emerald-600">✓ concorde</span>
                      ) : (
                        <span className="text-xs font-semibold text-amber-600">
                          ⚠ écart {money(a.control.diff, a.currency)}
                          <span className="ml-1 font-normal text-[var(--muted)]">
                            (implicite {money(a.control.implied, a.currency)})
                          </span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-3">
            <span className="text-xs text-[var(--muted)]">
              Ouverture d'exercice <b className="text-[var(--text)]">{eur(view.tie_out.opening_eur)}</b>{' '}
              → solde liquide actuel <b className="text-[var(--text)]">{eur(view.tie_out.current_eur)}</b>
              <span className="ml-1">
                (l'écart = conversions FX + charges + distributions de l'exercice ;
                le vrai contrôle exact est par compte ci-dessus).
              </span>
            </span>
            <button
              onClick={save}
              className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
            >
              Enregistrer les ouvertures {year}
            </button>
          </div>
        </>
      )}

      {status && <p className="mt-3 text-sm text-[var(--muted)]">{status}</p>}
      <p className="mt-2 text-[11px] text-[var(--muted)]">
        ℹ️ Comptes crypto (XRP) exclus — hors périmètre (saisie manuelle, NG6).
      </p>
    </Card>
  );
}
