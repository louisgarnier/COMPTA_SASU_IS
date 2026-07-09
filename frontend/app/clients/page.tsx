'use client';

import { useEffect, useState } from 'react';
import { clientsAPI, type RepricePreview } from '@/api/client';
import { PageTitle, Card, Empty, Badge } from '@/components/ui';
import { money, MONTH_LABELS } from '@/lib/format';

/** "2026-08" → "Août 2026". */
function monthLabel(m: string): string {
  const [y, mm] = m.split('-');
  return `${MONTH_LABELS[Number(mm) - 1] ?? mm} ${y}`;
}

type Client = {
  id: number;
  code: string;
  legal_name: string;
  address: string;
  city: string;
  state_region: string;
  postal_code: string;
  country: string;
  contact_name: string;
  email: string;
  currency: string;
  tjh: string | number;
  billing_mode: string;
  default_hours_per_day: string | number;
  payment_terms_days: number;
  pay_iban: string;
  pay_bic: string;
  pay_bank_name: string;
  pay_bank_address: string;
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
  { key: 'address', label: 'Adresse (rue)', group: 'Envoi facture', ph: '1 University Ave, Unit 11-101' },
  { key: 'city', label: 'Ville', group: 'Envoi facture', ph: 'Toronto' },
  { key: 'state_region', label: 'État / Région', group: 'Envoi facture', ph: 'ON' },
  { key: 'postal_code', label: 'Code postal', group: 'Envoi facture', ph: 'M5J 2P1' },
  { key: 'country', label: 'Pays', group: 'Envoi facture', ph: 'Canada' },
  { key: 'billing_mode', label: 'Mode', type: 'select', options: ['tjm', 'thm'], group: 'Facturation' },
  { key: 'tjh', label: 'Taux (jour/heure)', type: 'number', group: 'Facturation', ph: '120' },
  { key: 'default_hours_per_day', label: 'Heures / jour', type: 'number', group: 'Facturation', ph: '8' },
  { key: 'payment_terms_days', label: 'Échéance (jours)', type: 'number', group: 'Facturation', ph: '60' },
  { key: 'counterparty_match', label: 'Libellé rapprochement', group: 'Facturation', ph: 'texte relevé bancaire' },
  { key: 'pay_iban', label: 'IBAN de réception', group: 'Paiement', ph: 'FR76… (ton compte où ce client paie)' },
  { key: 'pay_bic', label: 'BIC', group: 'Paiement', ph: 'REVOFRP2' },
  { key: 'pay_bank_name', label: 'Banque', group: 'Paiement', ph: 'Revolut Bank UAB' },
  { key: 'pay_bank_address', label: 'Adresse banque', group: 'Paiement', ph: 'Konstitucijos ave. 21B, 08130 Vilnius…' },
];

const EMPTY: Partial<Client> = {
  code: '', legal_name: '', currency: 'USD', address: '', city: '', state_region: '', postal_code: '', country: '',
  contact_name: '', email: '', tjh: '', billing_mode: 'tjm',
  default_hours_per_day: 8, payment_terms_days: 60, counterparty_match: '', pay_iban: '', pay_bic: '', pay_bank_name: '', pay_bank_address: '',
};

// Libellé lisible pour les options de select.
const OPTION_LABEL: Record<string, string> = { tjm: 'TJM · jour', thm: 'THM · heure' };

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [form, setForm] = useState<Partial<Client>>(EMPTY);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [reprice, setReprice] = useState<RepricePreview | null>(null);
  const [repriceBusy, setRepriceBusy] = useState(false);

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
    if (!String(form.code ?? '').trim()) {
      setStatus('❌ Le code client est obligatoire');
      return;
    }
    setStatus('Enregistrement…');
    try {
      const payload: Record<string, unknown> = {};
      FIELDS.forEach((f) => {
        const v = form[f.key] ?? '';
        // Champ numérique laissé vide → on l'omet (le backend garde sa valeur /
        // son défaut) au lieu d'envoyer '' qui provoquait un 422.
        if (f.type === 'number' && v === '') return;
        payload[f.key] = v;
      });
      if (isEdit) {
        const orig = clients.find((c) => c.id === form.id);
        const rateOrModeChanged =
          !!orig &&
          (Number(orig.tjh) !== Number(form.tjh) ||
            orig.billing_mode !== form.billing_mode);
        await clientsAPI.update(form.id as number, payload);
        setStatus('✅ Enregistré');
        load();
        // Le taux ou le mode a changé → proposer de repropager aux prévisions futures.
        if (rateOrModeChanged) {
          const preview = await clientsAPI.repricePreview(form.id as number);
          if (preview.count > 0) setReprice(preview);
        }
      } else {
        const created = (await clientsAPI.create(payload)) as Client;
        setForm({ ...created });
        setStatus('✅ Enregistré');
        load();
      }
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    }
  }

  async function applyReprice() {
    if (!reprice || !form.id) return;
    setRepriceBusy(true);
    try {
      const res = await clientsAPI.reprice(form.id);
      setStatus(`✅ ${res.count} prévision(s) recalculée(s)`);
      setReprice(null);
    } catch (e) {
      setStatus(`❌ ${(e as Error).message}`);
    } finally {
      setRepriceBusy(false);
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

      {reprice && <RepriceModal data={reprice} clientCode={String(form.code ?? '')} busy={repriceBusy} onApply={applyReprice} onClose={() => setReprice(null)} />}
    </div>
  );
}

function RepriceModal({
  data,
  clientCode,
  busy,
  onApply,
  onClose,
}: {
  data: RepricePreview;
  clientCode: string;
  busy: boolean;
  onApply: () => void;
  onClose: () => void;
}) {
  const cur = data.currency;
  const first = data.rows[0];
  const oldRate =
    first && Number(first.quantity) > 0
      ? Number(first.old_amount) / Number(first.quantity)
      : null;
  const unitSuffix = data.rate_unit === 'hour' ? '/h' : '/j';
  const modeLabel = data.rate_unit === 'hour' ? 'THM · heure' : 'TJM · jour';
  const months = data.rows.map((r) => monthLabel(r.month));
  const span = months.length > 1 ? `${months[0]} à ${months[months.length - 1]}` : months[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 pb-2 pt-5">
          <h3 className="text-base font-semibold">Appliquer le nouveau taux aux prévisions à venir ?</h3>
          <p className="mt-1.5 text-sm text-[var(--muted)]">
            <b>{clientCode}</b> · taux{' '}
            {oldRate !== null && (
              <>
                <span className="text-[var(--muted)] line-through">{money(oldRate, cur)}</span>{' '}→{' '}
              </>
            )}
            <span className="font-semibold text-[var(--accent)]">{money(data.rate, cur)}{unitSuffix}</span> · mode <b>{modeLabel}</b>.
            <br />
            <b>{data.count} prévision(s)</b> — {span} seront recalculées.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted)]">
                <th className="px-5 py-2 text-left font-semibold">Mois</th>
                <th className="px-3 py-2 text-right font-semibold">Qté</th>
                <th className="px-3 py-2 text-right font-semibold">Ancien {cur}</th>
                <th className="px-3 py-2 text-right font-semibold">Nouveau {cur}</th>
                <th className="px-3 py-2 text-right font-semibold">Ancien €</th>
                <th className="px-5 py-2 text-right font-semibold">Nouveau €</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.month} className="border-b border-gray-100">
                  <td className="px-5 py-1.5 text-left">{monthLabel(r.month)}</td>
                  <td className="px-3 py-1.5 text-right">{Number(r.quantity)} {r.unit}</td>
                  <td className="px-3 py-1.5 text-right text-[var(--muted)]">{money(r.old_amount, cur)}</td>
                  <td className="px-3 py-1.5 text-right font-semibold">{money(r.new_amount, cur)}</td>
                  <td className="px-3 py-1.5 text-right text-[var(--muted)]">{money(r.old_amount_eur, 'EUR')}</td>
                  <td className="px-5 py-1.5 text-right font-semibold">{money(r.new_amount_eur, 'EUR')}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-[var(--border)] bg-gray-50 font-semibold">
                <td className="px-5 py-2 text-left">Total</td>
                <td></td>
                <td className="px-3 py-2 text-right text-[var(--muted)]">{money(data.total_old, cur)}</td>
                <td className="px-3 py-2 text-right">{money(data.total_new, cur)}</td>
                <td className="px-3 py-2 text-right text-[var(--muted)]">{money(data.total_old_eur, 'EUR')}</td>
                <td className="px-5 py-2 text-right">{money(data.total_new_eur, 'EUR')}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <p className="px-5 pt-3 text-xs text-[var(--muted)]">
          Les prévisions passées (avant le mois en cours) et les factures déjà générées ne sont pas touchées.
        </p>

        <div className="mt-2 flex justify-end gap-2.5 border-t border-gray-100 bg-gray-50 px-5 py-4">
          <button onClick={onClose} disabled={busy} className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--muted)] hover:bg-white disabled:opacity-50">
            Ne rien changer
          </button>
          <button onClick={onApply} disabled={busy} className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
            {busy ? 'Application…' : `Appliquer aux ${data.count} prévision(s)`}
          </button>
        </div>
      </div>
    </div>
  );
}
