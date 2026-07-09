'use client';

import { useEffect, useState } from 'react';
import { settingsAPI } from '@/api/client';
import { PageTitle, Card } from '@/components/ui';
import { FxRatesCard } from '@/components/FxRatesCard';
import { OpeningBalancesCard } from '@/components/OpeningBalancesCard';

const FIELDS: { key: string; label: string; type?: string; group: string; hint?: string }[] = [
  { key: 'company_name', label: 'Raison sociale', group: 'Société' },
  { key: 'siret', label: 'SIRET', group: 'Société' },
  { key: 'naf', label: 'Code NAF', group: 'Société' },
  { key: 'tva_intracom', label: 'TVA intracom', group: 'Société' },
  { key: 'address', label: 'Adresse', group: 'Société' },
  { key: 'email', label: 'Email', group: 'Société' },
  { key: 'capital_eur', label: 'Capital social (€)', type: 'number', group: 'Société' },
  { key: 'bank_name', label: 'Banque', group: 'Banque (réception)' },
  { key: 'bank_bic', label: 'BIC', group: 'Banque (réception)' },
  { key: 'bank_address', label: 'Adresse banque', group: 'Banque (réception)' },
  { key: 'is_low_rate', label: 'Taux IS réduit', type: 'number', group: 'Impôt société' },
  { key: 'is_threshold', label: 'Seuil IS (€)', type: 'number', group: 'Impôt société' },
  { key: 'is_high_rate', label: 'Taux IS normal', type: 'number', group: 'Impôt société' },
  { key: 'is_start_year', label: 'Début du régime IS (exercice)', type: 'number', group: 'Impôt société',
    hint: 'Avant cet exercice : régime IR — pas d\'IS société, pas de report à nouveau généré.' },
  { key: 'retained_earnings_eur', label: 'Stock à distribuer au 01/01 du 1er exercice IS (€)', type: 'number', group: 'Résultat & distribution',
    hint: 'Trésorerie/résultats de l\'ère IR restant à sortir. Soldé par les distributions ; le RAN se chaîne ensuite automatiquement.' },
  {
    key: 'next_invoice_number',
    label: 'Prochain n° de facture',
    type: 'number',
    group: 'Facturation',
    hint: 'Numéro de la prochaine facture émise. Réglez-le sur le n° suivant votre dernière facture existante pour reprendre votre séquence.',
  },
];

export default function SettingsPage() {
  const [data, setData] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<string>('');

  useEffect(() => {
    settingsAPI.get().then(setData).catch((e) => setStatus(`Erreur: ${e.message}`));
  }, []);

  const save = async () => {
    setStatus('Enregistrement…');
    try {
      const payload: Record<string, unknown> = {};
      FIELDS.forEach((f) => {
        const v = data[f.key];
        // Champ numérique vidé → on l'omet (évite un 422 sur tout le PUT).
        if (f.type === 'number' && (v === '' || v === null || v === undefined)) return;
        payload[f.key] = v;
      });
      const updated = await settingsAPI.update(payload);
      setData(updated);
      setStatus('✅ Enregistré');
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  };

  const groups = Array.from(new Set(FIELDS.map((f) => f.group)));

  return (
    <div className="max-w-2xl">
      <PageTitle
        title="Réglages"
        subtitle="Paramètres société, barèmes IS, facturation et change."
        action={
          <button onClick={save} className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90">
            Enregistrer
          </button>
        }
      />
      {status && <p className="mb-4 text-sm text-[var(--muted)]">{status}</p>}
      <div className="flex flex-col gap-5">
        {groups.map((g) => (
          <Card key={g}>
            <div className="mb-3 text-sm font-semibold">{g}</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {FIELDS.filter((f) => f.group === g).map((f) => (
                <label key={f.key} className="flex flex-col gap-1 text-sm">
                  <span className="text-[var(--muted)]">{f.label}</span>
                  <input
                    type={f.type ?? 'text'}
                    step="any"
                    value={String(data[f.key] ?? '')}
                    onChange={(e) => setData({ ...data, [f.key]: e.target.value })}
                    className="rounded-lg border border-[var(--border)] px-3 py-2 outline-none focus:border-[var(--accent)]"
                  />
                  {f.hint && <span className="text-xs text-[var(--muted)]">{f.hint}</span>}
                </label>
              ))}
            </div>
          </Card>
        ))}
        <FxRatesCard />
        <OpeningBalancesCard />
      </div>
    </div>
  );
}
