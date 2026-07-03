'use client';

import { useEffect, useState } from 'react';
import { clientsAPI } from '@/api/client';
import { PageTitle, Card, Empty, Badge } from '@/components/ui';

type Client = {
  id: number;
  code: string;
  legal_name: string;
  address: string;
  country: string;
  contact_name: string;
  email: string;
  currency: string;
  tjh: string | number;
  billing_mode: string;
  default_hours_per_day: string | number;
  payment_terms_days: number;
  pay_iban: string;
  counterparty_match: string;
};

type Field = {
  key: keyof Client;
  label: string;
  type?: string;
  group: string;
  ph?: string;
  options?: string[];
};

const CURRENCIES = ['EUR', 'USD', 'GBP', 'CAD', 'CHF'];

const FIELDS: Field[] = [
  { key: 'code', label: 'Code', group: 'Identité', ph: 'SWIB' },
  { key: 'legal_name', label: 'Raison sociale', group: 'Identité', ph: 'Alpha Financial…' },
  { key: 'currency', label: 'Devise', type: 'select', options: CURRENCIES, group: 'Identité' },
  { key: 'contact_name', label: 'Contact', group: 'Envoi facture', ph: 'Jane Doe' },
  { key: 'email', label: 'Email', group: 'Envoi facture', type: 'email', ph: 'billing@…' },
  { key: 'address', label: 'Adresse', group: 'Envoi facture', ph: '437 Madison Ave…' },
  { key: 'country', label: 'Pays', group: 'Envoi facture', ph: 'USA' },
  { key: 'billing_mode', label: 'Mode', type: 'select', options: ['tjm', 'thm'], group: 'Facturation' },
  { key: 'tjh', label: 'Taux (jour/heure)', type: 'number', group: 'Facturation', ph: '120' },
  { key: 'default_hours_per_day', label: 'Heures / jour', type: 'number', group: 'Facturation', ph: '8' },
  { key: 'payment_terms_days', label: 'Échéance (jours)', type: 'number', group: 'Facturation', ph: '60' },
  { key: 'counterparty_match', label: 'Libellé rapprochement', group: 'Facturation', ph: 'texte relevé bancaire' },
  { key: 'pay_iban', label: 'IBAN de réception', group: 'Paiement', ph: 'FR76… (ton compte où ce client paie)' },
];

const EMPTY: Partial<Client> = {
  code: '', legal_name: '', currency: 'USD', address: '', country: '',
  contact_name: '', email: '', tjh: '', billing_mode: 'tjm',
  default_hours_per_day: 8, payment_terms_days: 60, counterparty_match: '', pay_iban: '',
};

// Libellé lisible pour les options de select.
const OPTION_LABEL: Record<string, string> = { tjm: 'TJM · jour', thm: 'THM · heure' };

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [form, setForm] = useState<Partial<Client>>(EMPTY);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  async function load() {
    try {
      setClients((await clientsAPI.list()) as Client[]);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const isEdit = !!form.id;
  const groups = Array.from(new Set(FIELDS.map((f) => f.group)));

  function selectClient(c: Client) {
    setForm({ ...c });
    setStatus('');
  }
  function newClient() {
    setForm({ ...EMPTY });
    setStatus('');
  }

  async function save() {
    setStatus('Enregistrement…');
    try {
      const payload: Record<string, unknown> = {};
      FIELDS.forEach((f) => (payload[f.key] = form[f.key] ?? ''));
      if (isEdit) {
        await clientsAPI.update(form.id as number, payload);
      } else {
        const created = (await clientsAPI.create(payload)) as Client;
        setForm({ ...created });
      }
      setStatus('✅ Enregistré');
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function remove() {
    if (!form.id) return;
    if (!confirm(`Supprimer le client ${form.code} ?`)) return;
    try {
      await clientsAPI.remove(form.id);
      setStatus('🗑️ Supprimé');
      newClient();
      load();
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  return (
    <div>
      <PageTitle title="Clients" subtitle="Fiches clients — facturation & envoi" />
      {error && <p className="mb-4 text-sm text-[var(--neg)]">❌ {error}</p>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        {/* Liste */}
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Clients ({clients.length})</div>
            <button onClick={newClient} className="text-sm font-medium text-[var(--accent)]">
              + Nouveau
            </button>
          </div>
          {clients.length === 0 ? (
            <Empty>Aucun client.</Empty>
          ) : (
            <div className="flex flex-col gap-1">
              {clients.map((c) => (
                <button
                  key={c.id}
                  onClick={() => selectClient(c)}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-50 ${form.id === c.id ? 'bg-[var(--accent)]/10 font-medium' : ''}`}
                >
                  <span>
                    {c.legal_name || c.code} <span className="text-[var(--muted)]">· {c.code}</span>
                  </span>
                  <Badge>{c.currency}</Badge>
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Formulaire */}
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">{isEdit ? `Modifier ${form.code}` : 'Nouveau client'}</div>
            <div className="flex items-center gap-2">
              {isEdit && (
                <button onClick={remove} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--neg)] hover:bg-red-50">
                  Supprimer
                </button>
              )}
              <button onClick={save} className="rounded-lg bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white hover:opacity-90">
                Enregistrer
              </button>
            </div>
          </div>
          {status && <p className="mb-3 text-sm text-[var(--muted)]">{status}</p>}

          <div className="flex flex-col gap-5">
            {groups.map((g) => (
              <div key={g}>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{g}</div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {FIELDS.filter((f) => f.group === g).map((f) => (
                    <label key={f.key} className="flex flex-col gap-1 text-sm">
                      <span className="text-[var(--muted)]">{f.label}</span>
                      {f.type === 'select' ? (
                        <select
                          value={String(form[f.key] ?? '')}
                          onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                          className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 outline-none focus:border-[var(--accent)]"
                        >
                          {(f.options ?? []).map((o) => (
                            <option key={o} value={o}>
                              {OPTION_LABEL[o] ?? o}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={f.type ?? 'text'}
                          step={f.type === 'number' ? 'any' : undefined}
                          value={String(form[f.key] ?? '')}
                          placeholder={f.ph}
                          onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                          className="rounded-lg border border-[var(--border)] px-3 py-1.5 outline-none focus:border-[var(--accent)]"
                        />
                      )}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-[var(--muted)]">
            💡 L'<b>IBAN de réception</b> (ton compte où ce client paie, dans sa devise) s'imprimera sur la facture générée.
          </p>
        </Card>
      </div>
    </div>
  );
}
