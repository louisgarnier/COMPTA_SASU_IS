'use client';

import { useEffect, useMemo, useState } from 'react';
import { invoicesAPI, clientsAPI } from '@/api/client';
import { PageTitle, Card, StatCard, Badge, Empty } from '@/components/ui';
import { money, dateFR } from '@/lib/format';

type InvoiceStatus = 'draft' | 'sent' | 'paid';

interface Invoice {
  id: number;
  number: string;
  client_id: number;
  client_name: string;
  period_label: string;
  period_start: string;
  period_end: string;
  hours: number;
  rate: number;
  currency: string;
  amount: number;
  issue_date: string;
  due_date: string;
  status: InvoiceStatus;
  paid_transaction_id: number | null;
  pdf_path: string | null;
}

interface Client {
  id: number;
  code: string;
  legal_name: string;
  currency: string;
  tjh: number;
}

const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: 'Brouillon',
  sent: 'Envoyée',
  paid: 'Payée',
};

const STATUS_TONE: Record<InvoiceStatus, 'pos' | 'warn' | 'neutral'> = {
  paid: 'pos',
  sent: 'warn',
  draft: 'neutral',
};

const EMPTY_FORM = {
  client_id: '',
  period_label: '',
  period_start: '',
  period_end: '',
  hours: '',
  rate: '',
  currency: 'EUR',
};

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [form, setForm] = useState<typeof EMPTY_FORM>({ ...EMPTY_FORM });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string>('');
  // messages par facture : erreur PDF ou lien de téléchargement fraîchement généré
  const [pdfMsg, setPdfMsg] = useState<Record<number, string>>({});
  const [pdfReady, setPdfReady] = useState<Record<number, boolean>>({});

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [inv, cli] = await Promise.all([invoicesAPI.list(), clientsAPI.list()]);
      setInvoices(inv as Invoice[]);
      setClients(cli as Client[]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const liveAmount = useMemo(() => {
    const h = parseFloat(form.hours);
    const r = parseFloat(form.rate);
    if (!Number.isFinite(h) || !Number.isFinite(r)) return 0;
    return h * r;
  }, [form.hours, form.rate]);

  const totals = useMemo(() => {
    const total = invoices.reduce((s, i) => s + Number(i.amount || 0), 0);
    const paid = invoices.filter((i) => i.status === 'paid');
    const sent = invoices.filter((i) => i.status === 'sent');
    return {
      total,
      paidSum: paid.reduce((s, i) => s + Number(i.amount || 0), 0),
      paidCount: paid.length,
      sentSum: sent.reduce((s, i) => s + Number(i.amount || 0), 0),
      sentCount: sent.length,
    };
  }, [invoices]);

  const onClientChange = (id: string) => {
    const cli = clients.find((c) => String(c.id) === id);
    setForm((f) => ({
      ...f,
      client_id: id,
      currency: cli ? cli.currency : f.currency,
      rate: cli ? String(cli.tjh) : f.rate,
    }));
  };

  const create = async () => {
    setFormError('');
    if (!form.client_id) {
      setFormError('Sélectionnez un client.');
      return;
    }
    setCreating(true);
    try {
      await invoicesAPI.create({
        client_id: Number(form.client_id),
        period_label: form.period_label,
        period_start: form.period_start,
        period_end: form.period_end,
        hours: parseFloat(form.hours) || 0,
        rate: parseFloat(form.rate) || 0,
        currency: form.currency,
      });
      setForm({ ...EMPTY_FORM });
      await load();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const changeStatus = async (id: number, status: InvoiceStatus) => {
    try {
      const updated = (await invoicesAPI.update(id, { status })) as Invoice;
      setInvoices((list) => list.map((i) => (i.id === id ? { ...i, ...updated } : i)));
    } catch (e) {
      setPdfMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const makePdf = async (id: number) => {
    setPdfMsg((m) => ({ ...m, [id]: 'Génération…' }));
    try {
      const res = await invoicesAPI.generatePdf(id);
      setInvoices((list) =>
        list.map((i) => (i.id === id ? { ...i, pdf_path: res.pdf_path } : i)),
      );
      setPdfReady((r) => ({ ...r, [id]: true }));
      setPdfMsg((m) => ({ ...m, [id]: '' }));
    } catch (e) {
      setPdfMsg((m) => ({ ...m, [id]: `❌ ${(e as Error).message}` }));
    }
  };

  const inputCls =
    'rounded-lg border border-[var(--border)] px-3 py-2 outline-none focus:border-[var(--accent)]';

  return (
    <div>
      <PageTitle
        title="Factures"
        subtitle="Facturation clients — numérotation continue"
      />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total facturé" value={money(totals.total, 'EUR')} />
        <StatCard
          label={`Payées (${totals.paidCount})`}
          value={money(totals.paidSum, 'EUR')}
          tone="pos"
        />
        <StatCard
          label={`En attente (${totals.sentCount})`}
          value={money(totals.sentSum, 'EUR')}
          tone="neg"
        />
      </div>

      <Card className="mb-6">
        <div className="mb-3 text-sm font-semibold">Nouvelle facture</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Client</span>
            <select
              value={form.client_id}
              onChange={(e) => onClientChange(e.target.value)}
              className={inputCls}
            >
              <option value="">— Sélectionner —</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.legal_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Période</span>
            <input
              type="text"
              placeholder="Ex. Juin 2026"
              value={form.period_label}
              onChange={(e) => setForm({ ...form, period_label: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Devise</span>
            <input
              type="text"
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Début période</span>
            <input
              type="date"
              value={form.period_start}
              onChange={(e) => setForm({ ...form, period_start: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Fin période</span>
            <input
              type="date"
              value={form.period_end}
              onChange={(e) => setForm({ ...form, period_end: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Heures</span>
            <input
              type="number"
              step="any"
              value={form.hours}
              onChange={(e) => setForm({ ...form, hours: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Taux (TJH)</span>
            <input
              type="number"
              step="any"
              value={form.rate}
              onChange={(e) => setForm({ ...form, rate: e.target.value })}
              className={inputCls}
            />
          </label>
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--muted)]">Montant (calculé)</span>
            <div className="tabular rounded-lg border border-dashed border-[var(--border)] px-3 py-2 font-semibold">
              {money(liveAmount, form.currency || 'EUR')}
            </div>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={create}
            disabled={creating}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {creating ? 'Création…' : 'Créer'}
          </button>
          {formError && <span className="text-sm text-[var(--neg)]">❌ {formError}</span>}
        </div>
      </Card>

      {loading ? (
        <Empty>Chargement…</Empty>
      ) : error ? (
        <Empty>❌ {error}</Empty>
      ) : invoices.length === 0 ? (
        <Empty>Aucune facture pour le moment.</Empty>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                <th className="px-4 py-3 font-medium">N°</th>
                <th className="px-4 py-3 font-medium">Client</th>
                <th className="px-4 py-3 font-medium">Période</th>
                <th className="px-4 py-3 text-right font-medium">Montant</th>
                <th className="px-4 py-3 font-medium">Statut</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-4 py-3 font-medium tabular">{i.number}</td>
                  <td className="px-4 py-3">
                    <div>{i.client_name}</div>
                    <div className="text-xs text-[var(--muted)]">
                      {dateFR(i.issue_date)}
                    </div>
                  </td>
                  <td className="px-4 py-3">{i.period_label}</td>
                  <td className="px-4 py-3 text-right tabular">
                    {money(i.amount, i.currency)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[i.status]}>{STATUS_LABEL[i.status]}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={i.status}
                        onChange={(e) =>
                          changeStatus(i.id, e.target.value as InvoiceStatus)
                        }
                        className="rounded-lg border border-[var(--border)] px-2 py-1 text-xs outline-none focus:border-[var(--accent)]"
                      >
                        <option value="draft">Brouillon</option>
                        <option value="sent">Envoyée</option>
                        <option value="paid">Payée</option>
                      </select>
                      <button
                        onClick={() => makePdf(i.id)}
                        className="rounded-lg border border-[var(--border)] px-2 py-1 text-xs font-medium hover:border-[var(--accent)]"
                      >
                        PDF
                      </button>
                      {(i.pdf_path || pdfReady[i.id]) && (
                        <a
                          href={invoicesAPI.downloadUrl(i.id)}
                          className="rounded-lg px-2 py-1 text-xs font-medium text-[var(--accent)] underline hover:opacity-80"
                        >
                          Télécharger
                        </a>
                      )}
                      {pdfMsg[i.id] && (
                        <span className="text-xs text-[var(--neg)]">{pdfMsg[i.id]}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
