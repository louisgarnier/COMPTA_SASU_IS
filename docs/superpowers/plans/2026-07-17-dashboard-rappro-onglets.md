# Fusion « Soldes bancaires » + « Rapprochement mensuel » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sur le dashboard, la carte « Soldes bancaires à une date » gagne une pilule à 2 onglets dont le second affiche le rapprochement mensuel **en lecture seule**, avec un lien qui renvoie à la carte complète sur la page Banques.

**Architecture :** Le tableau 12 mois est extrait de `MonthlyReconcileCard` en composant présentationnel partagé (`MonthlyReconcileTable`). Deux consommateurs : la carte Banques (inchangée fonctionnellement — dépôt, sélection, envoi) et une vue dashboard lecture seule (`MonthlyReconcileView`). La carte dashboard (`BankBalancesCard`) n'est qu'une coquille : `<Card>` + pilule + bascule entre les deux onglets. L'onglet 2 ne `fetch` qu'à son ouverture (rendu conditionnel) — le dashboard ne paie pas l'appel réseau tant qu'on ne clique pas.

**Tech Stack :** Next.js 16 App Router, React 19, TypeScript, Tailwind v4, Jest + Testing Library.

## Global Constraints

- Maquette validée : variante **A** (consultation seule). Pas de dropzone, pas de cases à cocher, pas de barre d'envoi sur le dashboard.
- Aucun changement backend. Aucun changement du contrat `/api/monthly-balances/reconciliation`.
- Aucune régression sur la carte Banques : les 6 tests de `frontend/__tests__/monthly-reconcile.test.tsx` doivent rester verts **sans être modifiés** (ils sont le filet de la Task 1).
- Types existants réutilisés depuis `@/api/client` : `MonthlyReconView`, `MonthlyMonth`, `MonthlyAccountRow`, `MonthlyDoc`, `ReconStatus` (`'ok' | 'warn' | 'partial' | 'missing' | 'empty'`). Ne pas les redéclarer.
- Montants par compte en **devise native** via `money(v, currency)` ; totaux mensuels en **€** via `eur(v)`. Ne jamais formater un solde USD en euros (régression déjà corrigée, commit `76663e3`).
- Ancre de navigation : `id="rappro-mensuel"`, lien `/banking#rappro-mensuel`.
- Le travail se fait sur la branche courante `epic-8-rappro-mensuel-officiel`. Git **uniquement** via `python3 scripts/git_ops.py`. Format de commit : `[EPIC-8] type: description courte`.
- Toutes les commandes de test se lancent depuis `frontend/`.

## File Structure

| Fichier | Sort | Responsabilité |
|---|---|---|
| `frontend/src/components/MonthlyReconcileTable.tsx` | **Créé** | Tableau 12 mois présentationnel + dépliage détail par compte + badges. Aucun fetch. Colonne de sélection **optionnelle**. |
| `frontend/src/components/MonthlyReconcileCard.tsx` | Modifié | Garde dépôt/proposition/sélection/envoi. Délègue le tableau à `MonthlyReconcileTable` (`selectable`). |
| `frontend/src/components/dashboard/MonthlyReconcileView.tsx` | **Créé** | Onglet 2 du dashboard : fetch + sélecteur d'année + couverture + tableau lecture seule + lien « Déposer un relevé → ». |
| `frontend/src/components/dashboard/BalancesAtDate.tsx` | Modifié | Devient le **contenu** de l'onglet 1 : perd son wrapper `<Card>` et son titre (repris par la coquille). |
| `frontend/src/components/dashboard/BankBalancesCard.tsx` | **Créé** | Coquille : `<Card>` + pilule 2 onglets + bascule. |
| `frontend/app/page.tsx` | Modifié | Monte `BankBalancesCard` au lieu de `BalancesAtDate`. |
| `frontend/app/banking/page.tsx` | Modifié | Enveloppe `MonthlyReconcileCard` dans la cible d'ancre. |

---

### Task 1 : Extraire `MonthlyReconcileTable`

Refactoring pur : **aucun changement de comportement**. Les 6 tests existants de `monthly-reconcile.test.tsx` valident l'extraction sans être touchés.

**Files:**
- Create: `frontend/src/components/MonthlyReconcileTable.tsx`
- Modify: `frontend/src/components/MonthlyReconcileCard.tsx`
- Test: `frontend/__tests__/monthly-reconcile.test.tsx` *(non modifié — filet de sécurité)*

**Interfaces:**
- Consumes: `MonthlyReconView`, `MonthlyMonth`, `ReconStatus`, `balanceDocsAPI.downloadUrl` depuis `@/api/client` ; `Badge` depuis `@/components/ui` ; `eur`, `money` depuis `@/lib/format`.
- Produces:
  - `export const MOIS: string[]` — `['Janv','Févr','Mars','Avr','Mai','Juin','Juil','Août','Sept','Oct','Nov','Déc']`
  - `export function badgeFor(s: ReconStatus): JSX.Element`
  - `export function MonthlyReconcileTable(props: { view: MonthlyReconView; selectable?: boolean; selected?: Set<number>; onToggleMonth?: (m: number) => void; onToggleAll?: () => void; allSelected?: boolean; hasSelectableMonths?: boolean }): JSX.Element`

- [ ] **Step 1 : Vérifier que la suite est verte AVANT de toucher quoi que ce soit**

Run : `cd frontend && npx jest __tests__/monthly-reconcile.test.tsx`
Expected : `Tests: 6 passed`. Si ce n'est pas vert, **stop** — signaler, ne pas commencer le refactoring.

- [ ] **Step 2 : Créer le composant tableau**

Créer `frontend/src/components/MonthlyReconcileTable.tsx` :

```tsx
'use client';

import { Fragment, useState } from 'react';
import { balanceDocsAPI, type MonthlyReconView, type ReconStatus } from '@/api/client';
import { Badge } from '@/components/ui';
import { eur, money } from '@/lib/format';

export const MOIS = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'];

export const badgeFor = (s: ReconStatus) =>
  s === 'ok' ? <Badge tone="pos">✓ ok</Badge>
  : s === 'warn' ? <Badge tone="warn">⚠ écart</Badge>
  : s === 'partial' ? <Badge tone="info">partiel</Badge>
  : s === 'empty' ? <Badge tone="neutral">—</Badge>
  : <Badge tone="neutral">manquant</Badge>;

/**
 * Tableau 12 mois du rapprochement officiel — présentationnel, aucun fetch.
 * Partagé entre la carte Banques (`selectable` : cases à cocher pour l'envoi
 * groupé) et l'onglet lecture seule du dashboard (sans sélection).
 * Le dépliage du détail par compte est un état interne : les deux vues le veulent.
 */
export function MonthlyReconcileTable({
  view,
  selectable = false,
  selected,
  onToggleMonth,
  onToggleAll,
  allSelected = false,
  hasSelectableMonths = false,
}: {
  view: MonthlyReconView;
  selectable?: boolean;
  selected?: Set<number>;
  onToggleMonth?: (m: number) => void;
  onToggleAll?: () => void;
  allSelected?: boolean;
  hasSelectableMonths?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const cols = selectable ? 6 : 5;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            {selectable && (
              <th className="w-8 py-2 pr-2 font-medium">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  disabled={!hasSelectableMonths}
                  aria-label="Tout sélectionner"
                />
              </th>
            )}
            <th className="py-2 pr-4 font-medium">Fin de mois</th>
            <th className="py-2 pr-4 text-right font-medium">Solde officiel (€)</th>
            <th className="py-2 pr-4 text-right font-medium">Écart</th>
            <th className="py-2 pr-4 font-medium">Statut</th>
            <th className="py-2 font-medium">Relevés</th>
          </tr>
        </thead>
        <tbody>
          {view.months.map((m) => (
            <Fragment key={m.month}>
              <tr
                className={`cursor-pointer border-b border-[var(--border)] last:border-0 ${
                  selected?.has(m.month) ? 'bg-blue-50' : 'hover:bg-black/[0.02]'
                }`}
                onClick={() => setOpen(open === m.month ? null : m.month)}
              >
                {selectable && (
                  <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                    {m.docs.length > 0 && (
                      <input
                        type="checkbox"
                        checked={selected?.has(m.month) ?? false}
                        onChange={() => onToggleMonth?.(m.month)}
                        aria-label={`Sélectionner ${MOIS[m.month - 1]} ${view.year}`}
                      />
                    )}
                  </td>
                )}
                <td className="py-2 pr-4">{MOIS[m.month - 1]} {view.year}</td>
                <td className="tabular py-2 pr-4 text-right">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_official)}
                </td>
                <td className="tabular py-2 pr-4 text-right">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_diff)}
                </td>
                <td className="py-2 pr-4">{badgeFor(m.status)}</td>
                <td className="py-2" onClick={(e) => e.stopPropagation()}>
                  {m.docs.length > 0 ? (
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                      {m.docs.map((d, i) => (
                        <Fragment key={d.id}>
                          {i > 0 && <span className="text-[var(--muted)]">·</span>}
                          <a
                            href={balanceDocsAPI.downloadUrl(d.id)}
                            title={d.filename}
                            className="text-[var(--accent)] hover:underline"
                          >
                            ⬇ {d.name}
                          </a>
                        </Fragment>
                      ))}
                    </span>
                  ) : (
                    <span className="text-[var(--muted)]">—</span>
                  )}
                </td>
              </tr>
              {open === m.month && m.per_account.length > 0 && (
                <tr className="border-b border-[var(--border)] bg-black/[0.02] last:border-0">
                  <td colSpan={cols} className="px-3 pb-3">
                    <table className="w-full text-xs">
                      <tbody>
                        {m.per_account.map((a) => (
                          <tr key={a.account_uid} className="border-t border-[var(--border)]">
                            <td className="py-1 pr-2">{a.currency}</td>
                            <td className="tabular py-1 pr-2 text-right">
                              {a.official == null ? '—' : money(a.official, a.currency)}
                            </td>
                            <td className="tabular py-1 pr-2 text-right">{money(a.reconstructed, a.currency)}</td>
                            <td className="tabular py-1 pr-2 text-right">
                              {a.diff == null ? '—' : money(a.diff, a.currency)}
                            </td>
                            <td className="py-1">{badgeFor(a.status)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3 : Brancher la carte Banques sur le tableau extrait**

Dans `frontend/src/components/MonthlyReconcileCard.tsx` :

3a. Remplacer le bloc d'imports du haut (lignes 1-17, jusqu'à la fin de `badgeFor` incluse) par :

```tsx
'use client';

import { Fragment, useEffect, useState } from 'react';
import { balanceDocsAPI, monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { money } from '@/lib/format';
import { MOIS, MonthlyReconcileTable } from '@/components/MonthlyReconcileTable';

type ExtractedRow = { account_uid: string; currency: string; amount: string; matched?: boolean; hint?: string };
```

> `MOIS` reste utilisé par le `<select>` du mois de dépôt. `eur` et `badgeFor` ne servent plus ici (partis dans le tableau) — les retirer évite l'erreur lint `no-unused-vars`. `Fragment` et `Badge` servent encore dans le bloc « Soldes proposés ». `money` sert dans la proposition.

3b. Supprimer l'état `open` (`const [open, setOpen] = useState<number | null>(null);`, ligne ~24) — il vit désormais dans le tableau.

3c. Remplacer tout le bloc `<div className="overflow-x-auto">…</div>` final (de la ligne `<div className="overflow-x-auto">` jusqu'au `</div>` qui précède `</Card>`) par :

```tsx
      <MonthlyReconcileTable
        view={view}
        selectable
        selected={selected}
        onToggleMonth={toggleMonth}
        onToggleAll={toggleAll}
        allSelected={allSelected}
        hasSelectableMonths={monthsWithDocs.length > 0}
      />
```

- [ ] **Step 4 : Vérifier que le filet tient**

Run : `cd frontend && npx jest __tests__/monthly-reconcile.test.tsx`
Expected : `Tests: 6 passed` — les mêmes 6 qu'au Step 1, sans qu'une seule ligne de test ait bougé. Si un test casse, l'extraction a changé un comportement : corriger le composant, **pas le test**.

- [ ] **Step 5 : Vérifier les types**

Run : `cd frontend && npx tsc --noEmit`
Expected : aucune sortie.

- [ ] **Step 6 : Commit**

```bash
cd /Users/louisgarnier/Claude/compta_sasu
python3 scripts/git_ops.py commit "[EPIC-8] refactor: extraire MonthlyReconcileTable (tableau 12 mois partageable)" \
  frontend/src/components/MonthlyReconcileTable.tsx \
  frontend/src/components/MonthlyReconcileCard.tsx
```

---

### Task 2 : Vue lecture seule `MonthlyReconcileView` (onglet 2)

**Files:**
- Create: `frontend/src/components/dashboard/MonthlyReconcileView.tsx`
- Test: `frontend/__tests__/monthly-reconcile-view.test.tsx` *(créé)*

**Interfaces:**
- Consumes: `MonthlyReconcileTable` (Task 1) ; `monthlyBalancesAPI.reconciliation(year)` → `Promise<MonthlyReconView>`.
- Produces: `export function MonthlyReconcileView(props: { year: number }): JSX.Element`

- [ ] **Step 1 : Écrire le test qui échoue**

Créer `frontend/__tests__/monthly-reconcile-view.test.tsx` :

```tsx
import type { ReactNode } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MonthlyReconcileView } from '@/components/dashboard/MonthlyReconcileView';

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock('@/api/client', () => ({
  balanceDocsAPI: { downloadUrl: (id: number) => `/api/balance-docs/${id}/download` },
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025,
      coverage: '4/12',
      months: [
        {
          month: 10, status: 'warn', total_eur_official: '121880.10', total_eur_diff: '-23.00',
          per_account: [{
            account_uid: 'acc-usd', currency: 'USD', official: '80381.99',
            reconstructed: '80400.00', diff: '-18.01', status: 'warn',
          }],
          docs: [{ id: 7, name: 'Revolut', filename: 'releve-oct.pdf' }],
        },
        {
          month: 12, status: 'ok', total_eur_official: '126493.91', total_eur_diff: '0.00',
          per_account: [], docs: [],
        },
      ],
    }),
  },
}));

test('affiche la couverture et le tableau des mois', async () => {
  render(<MonthlyReconcileView year={2025} />);
  expect(await screen.findByText('4/12')).toBeInTheDocument();
  expect(await screen.findByText(/Oct 2025/)).toBeInTheDocument();
  expect(await screen.findByText(/Déc 2025/)).toBeInTheDocument();
});

test('lecture seule : aucune case à cocher, aucun dépôt de relevé', async () => {
  render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Déposer un relevé/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Envoyer par mail/i })).not.toBeInTheDocument();
});

test('le lien « Déposer un relevé » pointe sur la carte de la page Banques', async () => {
  render(<MonthlyReconcileView year={2025} />);
  const link = await screen.findByRole('link', { name: /Déposer un relevé/i });
  expect(link).toHaveAttribute('href', '/banking#rappro-mensuel');
});

test('le sélecteur d’année recharge la vue', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2025);

  fireEvent.click(await screen.findByRole('button', { name: '2024' }));
  await waitFor(() => expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2024));
});

test('les montants par compte restent en devise native', async () => {
  render(<MonthlyReconcileView year={2025} />);
  fireEvent.click(await screen.findByText(/Oct 2025/));
  expect(await screen.findByText(/80 381,99\s*\$US/)).toBeInTheDocument();
  expect(screen.queryByText(/80 381,99\s*€/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `cd frontend && npx jest __tests__/monthly-reconcile-view.test.tsx`
Expected : FAIL — `Cannot find module '@/components/dashboard/MonthlyReconcileView'`.

- [ ] **Step 3 : Écrire le composant**

Créer `frontend/src/components/dashboard/MonthlyReconcileView.tsx` :

```tsx
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { MonthlyReconcileTable } from '@/components/MonthlyReconcileTable';

/**
 * Onglet « Rapprochement mensuel » du dashboard — consultation seule
 * (maquette variante A, validée 2026-07-17). Le dépôt de relevé, la sélection
 * et l'envoi restent sur la page Banques : ici on regarde, on n'écrit pas.
 */
export function MonthlyReconcileView({ year: initialYear }: { year: number }) {
  const [year, setYear] = useState(initialYear);
  const currentYear = new Date().getFullYear();
  const yearOptions = [currentYear - 2, currentYear - 1, currentYear];
  const [view, setView] = useState<MonthlyReconView | null>(null);

  useEffect(() => {
    monthlyBalancesAPI.reconciliation(year).then(setView).catch(() => setView(null));
  }, [year]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex overflow-hidden rounded-lg border border-[var(--border)]">
          {yearOptions.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => setYear(y)}
              className={`border-r border-[var(--border)] px-3 py-1 text-xs font-semibold last:border-r-0 ${
                y === year ? 'bg-[var(--accent)] text-white' : 'bg-white text-[var(--text)] hover:bg-gray-50'
              }`}
            >
              {y}
            </button>
          ))}
        </div>
        <span className="text-xs text-[var(--muted)]">
          Couverture <strong className="text-[var(--text)]">{view?.coverage ?? '—'}</strong> mois
        </span>
      </div>

      {view ? (
        <MonthlyReconcileTable view={view} />
      ) : (
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      )}

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <Link href="/banking#rappro-mensuel" className="text-xs font-semibold text-[var(--accent)] hover:underline">
          Déposer un relevé →
        </Link>
        <span className="ml-1.5 text-[11px] text-[var(--muted)]">(page Banques)</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4 : Lancer le test pour le voir passer**

Run : `cd frontend && npx jest __tests__/monthly-reconcile-view.test.tsx`
Expected : `Tests: 5 passed`.

- [ ] **Step 5 : Commit**

```bash
cd /Users/louisgarnier/Claude/compta_sasu
python3 scripts/git_ops.py commit "[EPIC-8] feat: vue rapprochement mensuel lecture seule pour le dashboard" \
  frontend/src/components/dashboard/MonthlyReconcileView.tsx \
  frontend/__tests__/monthly-reconcile-view.test.tsx
```

---

### Task 3 : Coquille `BankBalancesCard` avec la pilule 2 onglets

**Files:**
- Create: `frontend/src/components/dashboard/BankBalancesCard.tsx`
- Modify: `frontend/src/components/dashboard/BalancesAtDate.tsx`
- Modify: `frontend/app/page.tsx:239`
- Test: `frontend/__tests__/bank-balances-card.test.tsx` *(créé)*, `frontend/__tests__/dashboard.test.tsx` *(mock à compléter)*

**Interfaces:**
- Consumes: `BalancesAtDate` (contenu de l'onglet 1, sans `<Card>`) ; `MonthlyReconcileView` (Task 2).
- Produces: `export function BankBalancesCard(props: { year?: number }): JSX.Element`
- Breaking : `BalancesAtDate` ne rend plus son propre `<Card>` ni son titre. Seul `BankBalancesCard` la consomme.

- [ ] **Step 1 : Écrire le test qui échoue**

Créer `frontend/__tests__/bank-balances-card.test.tsx` :

```tsx
import type { ReactNode } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BankBalancesCard } from '@/components/dashboard/BankBalancesCard';

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock('@/api/client', () => ({
  balanceDocsAPI: { downloadUrl: (id: number) => `/api/balance-docs/${id}/download` },
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({
      as_of: '2025-12-31',
      bank_total_eur: '126493.91',
      accounts: [{
        account_uid: 'cd56227f-c427', name: 'Revolut Main', provider: 'revolut',
        currency: 'EUR', balance: '11626.90', balance_eur: '11626.90',
      }],
    }),
  },
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025, coverage: '4/12',
      months: [{
        month: 12, status: 'ok', total_eur_official: '126493.91',
        total_eur_diff: '0.00', per_account: [], docs: [],
      }],
    }),
  },
}));

test('ouvre sur l’onglet Soldes à une date', async () => {
  render(<BankBalancesCard year={2025} />);
  expect(await screen.findByText('11 626,90 €')).toBeInTheDocument();
  // L'onglet rappro n'est pas monté tant qu'on ne clique pas.
  expect(screen.queryByText(/Couverture/)).not.toBeInTheDocument();
});

test('la pilule bascule sur le rapprochement mensuel', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  render(<BankBalancesCard year={2025} />);
  await screen.findByText('11 626,90 €');

  fireEvent.click(screen.getByRole('button', { name: /Rapprochement mensuel/i }));
  expect(await screen.findByText('4/12')).toBeInTheDocument();
  expect(await screen.findByText(/Déc 2025/)).toBeInTheDocument();
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalled();
});

test('la pilule revient sur les soldes', async () => {
  render(<BankBalancesCard year={2025} />);
  await screen.findByText('11 626,90 €');
  fireEvent.click(screen.getByRole('button', { name: /Rapprochement mensuel/i }));
  await screen.findByText('4/12');

  fireEvent.click(screen.getByRole('button', { name: /Soldes à une date/i }));
  expect(await screen.findByText('11 626,90 €')).toBeInTheDocument();
  expect(screen.queryByText('4/12')).not.toBeInTheDocument();
});
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `cd frontend && npx jest __tests__/bank-balances-card.test.tsx`
Expected : FAIL — `Cannot find module '@/components/dashboard/BankBalancesCard'`.

- [ ] **Step 3 : Déshabiller `BalancesAtDate` de son `<Card>`**

Dans `frontend/src/components/dashboard/BalancesAtDate.tsx` :

3a. Import : retirer `Card` (garder `Badge`) —
`import { Card, Badge } from '@/components/ui';` → `import { Badge } from '@/components/ui';`

3b. Remplacer l'ouverture du rendu (lignes 46-47) —

```tsx
    <Card>
      <div className="mb-1 text-sm font-semibold">Soldes bancaires à une date</div>
```
par :
```tsx
    <div>
```

3c. Remplacer le `</Card>` final (ligne 107) par `</div>`.

> Le titre part dans la coquille, la pilule le remplace. Le commentaire JSDoc du composant reste valide.

- [ ] **Step 4 : Écrire la coquille**

Créer `frontend/src/components/dashboard/BankBalancesCard.tsx` :

```tsx
'use client';

import { useState } from 'react';
import { Card } from '@/components/ui';
import { BalancesAtDate } from '@/components/dashboard/BalancesAtDate';
import { MonthlyReconcileView } from '@/components/dashboard/MonthlyReconcileView';

type Tab = 'soldes' | 'rappro';

const TABS: { id: Tab; label: string }[] = [
  { id: 'soldes', label: 'Soldes à une date' },
  { id: 'rappro', label: 'Rapprochement mensuel' },
];

/**
 * Carte « Soldes bancaires » du dashboard : deux lectures du même sujet.
 * — « Soldes à une date » : reconstruction à la date choisie.
 * — « Rapprochement mensuel » : officiel vs reconstitué, 12 mois (lecture seule).
 * L'onglet rappro n'est monté qu'à son ouverture : le dashboard ne paie pas
 * son appel réseau tant qu'on ne le demande pas.
 */
export function BankBalancesCard({ year }: { year?: number }) {
  const [tab, setTab] = useState<Tab>('soldes');
  const curYear = new Date().getFullYear();
  const selYear = year && year <= curYear ? year : curYear;

  return (
    <Card>
      <div className="mb-3 inline-flex gap-1 rounded-xl bg-gray-100 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              tab === t.id
                ? 'bg-white text-[var(--accent)] shadow-sm'
                : 'text-[var(--muted)] hover:text-[var(--text)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'soldes' ? <BalancesAtDate year={year} /> : <MonthlyReconcileView year={selYear} />}
    </Card>
  );
}
```

- [ ] **Step 5 : Lancer le test pour le voir passer**

Run : `cd frontend && npx jest __tests__/bank-balances-card.test.tsx`
Expected : `Tests: 3 passed`.

- [ ] **Step 6 : Monter la coquille sur le dashboard**

Dans `frontend/app/page.tsx` :

6a. Ligne 17 —
`import { BalancesAtDate } from '@/components/dashboard/BalancesAtDate';`
→ `import { BankBalancesCard } from '@/components/dashboard/BankBalancesCard';`

6b. Ligne 239 —
`        <BalancesAtDate year={year} />`
→ `        <BankBalancesCard year={year} />`

- [ ] **Step 7 : Compléter le mock de `dashboard.test.tsx`**

`dashboard.test.tsx` mocke `@/api/client` en entier ; la carte tire maintenant `monthlyBalancesAPI` et `balanceDocsAPI`. Sans eux, un clic sur l'onglet planterait. Ajouter dans l'objet du `jest.mock('@/api/client', …)`, juste après le bloc `treasuryAPI` :

```tsx
  balanceDocsAPI: { downloadUrl: (id: number) => `/api/balance-docs/${id}/download` },
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2026, coverage: '0/12', months: [],
    }),
  },
```

L'assertion existante ligne 118 (`expect(screen.getByText('Soldes bancaires à une date'))`) **va casser** : ce titre n'existe plus, il est devenu l'onglet « Soldes à une date ». La remplacer par :

```tsx
    // Carte soldes bancaires : la pilule et le total de l'onglet par défaut.
    expect(screen.getByRole('button', { name: /Soldes à une date/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Rapprochement mensuel/i })).toBeInTheDocument();
```

> Garder l'assertion du total qui suit ligne 119 si elle porte sur un montant — seul le titre change.

- [ ] **Step 8 : Vérifier la suite front complète + les types**

Run : `cd frontend && npx jest && npx tsc --noEmit`
Expected : toutes les suites vertes (les 14 existantes + 2 nouvelles), aucune sortie `tsc`.

- [ ] **Step 9 : Commit**

```bash
cd /Users/louisgarnier/Claude/compta_sasu
python3 scripts/git_ops.py commit "[EPIC-8] feat: carte dashboard Soldes bancaires — pilule 2 onglets (soldes / rappro)" \
  frontend/src/components/dashboard/BankBalancesCard.tsx \
  frontend/src/components/dashboard/BalancesAtDate.tsx \
  frontend/app/page.tsx \
  frontend/__tests__/bank-balances-card.test.tsx \
  frontend/__tests__/dashboard.test.tsx
```

---

### Task 4 : Ancre `#rappro-mensuel` sur la page Banques

Ferme la boucle : le lien de la Task 2 doit atterrir **sur** la carte, pas en haut de la page.

**Files:**
- Modify: `frontend/app/banking/page.tsx:416-417`
- Test: `frontend/__tests__/banking.test.tsx` *(assertion ajoutée)*

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: cible d'ancre `id="rappro-mensuel"` sur la page `/banking`.

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à la fin de `frontend/__tests__/banking.test.tsx` :

```tsx
test('la carte rappro porte l’ancre visée par le lien du dashboard', async () => {
  const { container } = render(<BankingPage />);
  await waitFor(() => expect(container.querySelector('#rappro-mensuel')).not.toBeNull());
  // scroll-margin : la barre de nav mobile fixe (Nav.tsx) ne doit pas recouvrir
  // la carte à l'arrivée sur l'ancre.
  expect(container.querySelector('#rappro-mensuel')).toHaveClass('scroll-mt-20');
});
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `cd frontend && npx jest __tests__/banking.test.tsx`
Expected : FAIL — le sélecteur `#rappro-mensuel` reste `null`.

- [ ] **Step 3 : Poser l'ancre**

Dans `frontend/app/banking/page.tsx`, remplacer les lignes 416-417 :

```tsx
          {/* Rapprochement mensuel officiel */}
          <MonthlyReconcileCard year={new Date().getFullYear()} />
```
par :
```tsx
          {/* Rapprochement mensuel officiel — cible du lien « Déposer un relevé → »
              de la carte Soldes bancaires du dashboard. `scroll-mt-20` dégage la
              barre de nav mobile fixe (Nav.tsx) à l'arrivée sur l'ancre. */}
          <div id="rappro-mensuel" className="scroll-mt-20">
            <MonthlyReconcileCard year={new Date().getFullYear()} />
          </div>
```

- [ ] **Step 4 : Lancer le test pour le voir passer**

Run : `cd frontend && npx jest __tests__/banking.test.tsx`
Expected : toutes les assertions de la suite passent, dont la nouvelle.

- [ ] **Step 5 : Vérifier la suite complète + le build**

Run : `cd frontend && npx jest && npx tsc --noEmit && npx next build`
Expected : toutes les suites vertes, `tsc` muet, build OK.

- [ ] **Step 6 : Commit**

```bash
cd /Users/louisgarnier/Claude/compta_sasu
python3 scripts/git_ops.py commit "[EPIC-8] feat: ancre #rappro-mensuel — le lien du dashboard atterrit sur la carte" \
  frontend/app/banking/page.tsx \
  frontend/__tests__/banking.test.tsx
```

---

## Vérification finale (avant de rendre la main)

Les tests jest ne prouvent pas qu'un humain voit la bonne chose. Exercer l'app pour de vrai :

- [ ] Vérifier les ports **avant** de lancer quoi que ce soit : `lsof -nP -iTCP:3001 -sTCP:LISTEN` et `lsof -nP -iTCP:8001 -sTCP:LISTEN`. Si occupés, sonder `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health` — si c'est LGC et qu'il répond `200`, **ne pas relancer**, réutiliser.
- [ ] Dashboard → carte « Soldes bancaires » : la pilule bascule, l'onglet 2 affiche les 12 mois de l'année sélectionnée, la carte ne change pas de hauteur au point de casser la grille (le point de la maquette).
- [ ] Cliquer « Déposer un relevé → » : on atterrit sur `/banking`, scrollé **sur** la carte rappro, dropzone visible et non recouverte par la barre de nav.
- [ ] Vérifier en 1024px de large **et** en mobile (< lg) que l'atterrissage sur l'ancre reste correct — c'est là que la barre fixe joue.
- [ ] Capturer une **capture d'écran** de chaque onglet + de l'atterrissage sur l'ancre pour la preuve de handoff.
- [ ] Mettre à jour `docs/project/config/build-log.md` (entrée du jour) et `docs/project/config/codebase.md` (3 nouveaux composants), puis commit `[EPIC-8] docs: …`.
