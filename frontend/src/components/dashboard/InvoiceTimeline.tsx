'use client';

import { Card, Empty } from '@/components/ui';
import { eur, money, MONTH_LABELS } from '@/lib/format';

const PAID = '#16a34a';
const DUE = '#eab308';
const OVER = '#dc2626';

type Month = {
  month: string;
  paid_eur: string | number;
  due_eur: string | number;
  overdue_eur: string | number;
};

type Open = {
  number: string;
  client_code: string;
  currency: string;
  amount: string | number;
  amount_eur: string | number;
  status: 'due' | 'overdue';
};

export type InvoiceTimelineData = {
  months: Month[];
  outstanding_eur: string | number;
  open: Open[];
  open_count: number;
};

const num = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : 0;
};

function monthLabel(m: string) {
  const idx = parseInt(m.slice(5, 7), 10) - 1;
  return MONTH_LABELS[idx] ?? m;
}

export function InvoiceTimeline({ data }: { data: InvoiceTimelineData }) {
  const H = 150;
  const max = Math.max(
    1,
    ...data.months.map((m) => num(m.paid_eur) + num(m.due_eur) + num(m.overdue_eur)),
  );
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold">Invoice Timeline</div>
        <div className="flex items-center gap-3 text-[11px] text-[var(--muted)]">
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: PAID }} />Payé</span>
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: DUE }} />Dû</span>
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: OVER }} />En retard</span>
        </div>
      </div>

      {data.months.length === 0 ? (
        <Empty>Aucune facture sur la période.</Empty>
      ) : (
        <div className="flex items-end gap-3.5" style={{ height: H + 20 }}>
          {data.months.map((m) => {
            const seg = (v: number, c: string) =>
              v > 0 ? (
                <div style={{ height: `${(v / max) * H}px`, background: c }} />
              ) : null;
            return (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1.5">
                <div
                  className="flex w-3/5 flex-col justify-end overflow-hidden rounded-t"
                  style={{ height: H }}
                  title={`${monthLabel(m.month)} — Payé ${eur(m.paid_eur)} · Dû ${eur(m.due_eur)} · Retard ${eur(m.overdue_eur)}`}
                >
                  {seg(num(m.overdue_eur), OVER)}
                  {seg(num(m.due_eur), DUE)}
                  {seg(num(m.paid_eur), PAID)}
                </div>
                <div className="text-[10px] text-[var(--muted)]">{monthLabel(m.month)}</div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-2 flex items-center justify-between border-t border-[var(--border)] pt-2.5">
        <span className="text-sm font-medium text-[var(--accent)]">+ Nouvelle facture</span>
        <span className="text-xs text-[var(--muted)]">
          En attente <b className="tabular text-[var(--text)]">{eur(data.outstanding_eur)}</b> ·{' '}
          {data.open_count} ouverte{data.open_count > 1 ? 's' : ''}
        </span>
      </div>
    </Card>
  );
}

export function OpenInvoices({ data }: { data: InvoiceTimelineData }) {
  return (
    <Card>
      <div className="mb-2 text-sm font-semibold">Factures ouvertes</div>
      {data.open.length === 0 ? (
        <Empty>Aucune facture en attente.</Empty>
      ) : (
        <div className="flex flex-col">
          {data.open.map((iv) => (
            <div
              key={iv.number}
              className="flex items-center justify-between border-t border-[var(--border)] py-2 text-sm first:border-t-0"
            >
              <span>
                <b>{iv.number}</b> <span className="text-[var(--muted)]">· {iv.client_code}</span>
              </span>
              <span className="flex items-center gap-2">
                <span
                  className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase"
                  style={
                    iv.status === 'overdue'
                      ? { background: '#fef2f2', color: OVER }
                      : { background: '#fefce8', color: '#a16207' }
                  }
                >
                  {iv.status === 'overdue' ? 'En retard' : 'Dû'}
                </span>
                <b className="tabular">{money(iv.amount, iv.currency)}</b>
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
