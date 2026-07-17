import type { ReactNode } from 'react';

export function PageTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[var(--muted)]">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-[var(--border)] bg-[var(--panel)] p-5 ${className}`}>
      {children}
    </div>
  );
}

export function StatCard({ label, value, tone = 'neutral' }: { label: string; value: ReactNode; tone?: 'neutral' | 'pos' | 'neg' }) {
  const color = tone === 'pos' ? 'text-[var(--pos)]' : tone === 'neg' ? 'text-[var(--neg)]' : 'text-[var(--text)]';
  return (
    <Card>
      <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className={`tabular mt-2 text-2xl font-semibold ${color}`}>{value}</div>
    </Card>
  );
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'pos' | 'neg' | 'warn' | 'info' }) {
  const map = {
    neutral: 'bg-gray-100 text-gray-700',
    pos: 'bg-green-100 text-green-700',
    neg: 'bg-red-100 text-red-700',
    warn: 'bg-amber-100 text-amber-700',
    info: 'bg-blue-100 text-blue-700',
  } as const;
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${map[tone]}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">{children}</div>;
}
