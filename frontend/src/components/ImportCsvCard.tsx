'use client';

import { useRef, useState } from 'react';
import { importApi, type ImportPreview, type ImportReport } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { money, dateFR } from '@/lib/format';

// Pas d'état "error" dédié : une erreur peut survenir pendant le chargement
// (retour à 'idle', carte 1) ou pendant l'import (retour à 'preview', carte 2,
// pour permettre de relancer sans re-uploader). Le message est porté par
// `error`, affiché dans la carte correspondant à `step` au moment de l'échec.
type Step = 'idle' | 'loading' | 'preview' | 'importing' | 'done';

const YEAR = 2025;

// Libellés d'affichage des banques détectées (codes techniques du backend).
const BANK_LABELS: Record<string, string> = {
  revolut: 'Revolut Business',
  qonto: 'Qonto',
};

function bankLabel(bank: string): string {
  return BANK_LABELS[bank.toLowerCase()] ?? bank;
}

function Tile({
  label,
  value,
  sub,
  testId,
}: {
  label: string;
  value: string;
  sub?: string;
  testId?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="tabular mt-1 text-base font-semibold" data-testid={testId}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

function Warnings({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
      <div className="mb-1 font-semibold">⚠ Avertissements</div>
      <ul className="list-inside list-disc">
        {items.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ImportCsvCard() {
  const [step, setStep] = useState<Step>('idle');
  const [fileName, setFileName] = useState('');
  const [content, setContent] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const readFile = (file: File) => {
    setError('');
    setFileName(file.name);
    setStep('loading');
    const reader = new FileReader();
    reader.onload = async () => {
      const text = String(reader.result ?? '');
      setContent(text);
      try {
        const res = await importApi.preview(text, YEAR);
        setPreview(res);
        setStep('preview');
      } catch (e) {
        setError((e as Error).message);
        setStep('idle');
      }
    };
    reader.onerror = () => {
      setError('Impossible de lire le fichier.');
      setStep('idle');
    };
    reader.readAsText(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) readFile(file);
    e.target.value = ''; // permet de re-sélectionner le même fichier
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) readFile(file);
  };

  const handleImport = async () => {
    setStep('importing');
    setError('');
    try {
      const res = await importApi.execute(content, YEAR);
      setReport(res);
      setStep('done');
    } catch (e) {
      setError((e as Error).message);
      setStep('preview');
    }
  };

  const reset = () => {
    setStep('idle');
    setFileName('');
    setContent('');
    setPreview(null);
    setReport(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const showPreview = (step === 'preview' || step === 'importing') && preview;

  return (
    <div className="flex flex-col gap-5">
      {/* 1. Fichier CSV */}
      <Card>
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-sm font-semibold">1. Fichier CSV</span>
          <Badge>Périmètre : exercice {YEAR}</Badge>
        </div>
        <div
          role="button"
          tabIndex={0}
          aria-label="Sélectionner ou déposer un fichier CSV"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            // Accessibilité clavier : Entrée/Espace ouvrent le sélecteur de fichier.
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          className="cursor-pointer rounded-lg border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)] hover:border-[var(--accent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          {step === 'loading' ? (
            <span>Lecture de {fileName}…</span>
          ) : (
            <span>
              Glissez-déposez un export CSV de votre banque ou cliquez pour
              sélectionner un fichier.
            </span>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            data-testid="import-file-input"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>
        {step === 'idle' && error && (
          <p className="mt-3 text-sm text-[var(--neg)]">❌ {error}</p>
        )}
      </Card>

      {/* 2. Prévisualisation */}
      {showPreview && (
        <Card>
          <div className="mb-3 text-sm font-semibold">2. Prévisualisation</div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Tile
              label="Banque détectée"
              value={bankLabel(preview.bank)}
              sub="colonnes reconnues ✓"
              testId="preview-bank"
            />
            <Tile
              label="Période du fichier"
              value={`${dateFR(preview.period.min)} → ${dateFR(preview.period.max)}`}
              sub={`${preview.rows_read} lignes lues`}
            />
            <Tile
              label="À importer"
              value={String(preview.importable)}
              sub={`${preview.out_of_period} hors période · ${preview.duplicates} doublon(s)`}
            />
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                  <th className="py-2 pr-4 font-medium">Compte (CSV)</th>
                  <th className="py-2 pr-4 font-medium">IBAN</th>
                  <th className="py-2 pr-4 font-medium">Devise</th>
                  <th className="py-2 pr-4 text-right font-medium">Transactions</th>
                  <th className="py-2 font-medium">Rattachement</th>
                </tr>
              </thead>
              <tbody>
                {preview.accounts.map((a) => (
                  <tr key={a.csv_name} className="border-b border-[var(--border)] last:border-0">
                    <td className="py-2 pr-4">{a.csv_name}</td>
                    <td className="tabular py-2 pr-4">{a.iban_masked}</td>
                    <td className="py-2 pr-4">{a.currency}</td>
                    <td className="tabular py-2 pr-4 text-right">{a.tx_count}</td>
                    <td className="py-2">
                      {a.matched ? (
                        <Badge tone="pos">Existant · {a.account_name}</Badge>
                      ) : (
                        <Badge tone="warn">Non rattaché</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {preview.sample.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-xs uppercase tracking-wide text-[var(--muted)]">
                Aperçu (5 premières lignes)
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                      <th className="py-2 pr-4 font-medium">Date</th>
                      <th className="py-2 pr-4 font-medium">Description</th>
                      <th className="py-2 pr-4 text-right font-medium">Montant</th>
                      <th className="py-2 font-medium">Compte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.slice(0, 5).map((s, i) => (
                      <tr key={i} className="border-b border-[var(--border)] last:border-0">
                        <td className="py-2 pr-4">{dateFR(s.date)}</td>
                        <td className="py-2 pr-4">{s.description}</td>
                        <td className="tabular py-2 pr-4 text-right">
                          {money(s.amount, s.currency)}
                        </td>
                        <td className="py-2">{s.account}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <Warnings items={preview.warnings} />

          {error && (
            <p className="mt-3 text-sm text-[var(--neg)]">❌ {error}</p>
          )}

          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={handleImport}
              disabled={step === 'importing' || preview.importable === 0}
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {step === 'importing'
                ? 'Import en cours…'
                : `Importer ${preview.importable} transactions`}
            </button>
            <button
              onClick={reset}
              disabled={step === 'importing'}
              className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)] disabled:opacity-50"
            >
              Annuler
            </button>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            🛟 Un backup de la base est créé automatiquement avant l&apos;import.
          </p>
        </Card>
      )}

      {/* 3. Rapport d'import */}
      {step === 'done' && report && (
        <Card>
          <div className="mb-3 text-sm font-semibold">3. Rapport d&apos;import</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Tile label="Insérées" value={String(report.inserted)} />
            <Tile label="Doublons ignorés" value={String(report.duplicates)} />
            <Tile label="Hors période" value={String(report.out_of_period)} />
            <Tile label="Catégorisées" value={String(report.categorized)} />
          </div>
          <p className="mt-3 text-sm text-[var(--muted)]">
            🛟 Backup : <span className="tabular">{report.backup_file}</span>
          </p>
          <Warnings items={report.warnings} />
          <div className="mt-4 flex items-center gap-3">
            <a
              href="/transactions"
              className="text-sm text-[var(--accent)] underline"
            >
              Voir les transactions {YEAR} →
            </a>
            <button
              onClick={reset}
              className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)]"
            >
              Importer un autre fichier
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
