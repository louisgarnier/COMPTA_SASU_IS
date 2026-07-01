'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { balanceDocsAPI } from '@/api/client';
import { dateFR } from '@/lib/format';

type Doc = {
  id: number;
  account_uid: string | null;
  label: string;
  doc_date: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
};

const humanSize = (n: number) =>
  n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1000))} Ko`;

export function BalanceDocsModal({ onClose }: { onClose: () => void }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    balanceDocsAPI
      .list()
      .then(setDocs)
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = useCallback(
    async (files: FileList | File[]) => {
      setBusy(true);
      setError('');
      try {
        for (const f of Array.from(files)) {
          await balanceDocsAPI.upload(f, { label: f.name });
        }
        load();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.length) upload(e.dataTransfer.files);
  };

  const remove = async (id: number) => {
    await balanceDocsAPI.remove(id);
    load();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-xl overflow-auto rounded-xl bg-[var(--panel)] p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Justificatifs de solde</h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)]">
            ✕
          </button>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center text-sm transition ${
            dragging
              ? 'border-[var(--accent)] bg-blue-50'
              : 'border-[var(--border)] text-[var(--muted)] hover:border-[var(--accent)]'
          }`}
        >
          {busy ? (
            'Téléversement…'
          ) : (
            <>
              📎 Glissez vos relevés PDF/images ici, ou cliquez pour choisir.
              <div className="mt-1 text-xs">PDF, PNG, JPG · max 20 Mo</div>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="application/pdf,image/*"
            className="hidden"
            onChange={(e) => e.target.files && upload(e.target.files)}
          />
        </div>

        {error && <p className="mt-3 text-sm text-[var(--neg)]">❌ {error}</p>}

        <div className="mt-5">
          {docs.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">Aucun justificatif pour l'instant.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--border)]">
              {docs.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{d.filename}</div>
                    <div className="text-xs text-[var(--muted)]">
                      {humanSize(d.size_bytes)}
                      {d.doc_date ? ` · ${dateFR(d.doc_date)}` : ''}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 text-sm">
                    <a
                      href={balanceDocsAPI.downloadUrl(d.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[var(--accent)] hover:underline"
                    >
                      Ouvrir
                    </a>
                    <button
                      onClick={() => remove(d.id)}
                      className="text-[var(--neg)] hover:underline"
                    >
                      Supprimer
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
