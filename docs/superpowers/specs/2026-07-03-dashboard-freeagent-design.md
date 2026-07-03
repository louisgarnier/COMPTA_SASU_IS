# Dashboard FreeAgent × multi-devise — Design

**Date:** 2026-07-03
**Status:** Approved (mockup v3 validé)
**Epic:** EPIC-4 (dashboard / pilotage)

## Goal

Remplacer le dashboard actuel (P&L empilé par devise + combo « Prévision tréso ») par
une structure inspirée de **FreeAgent** : des widgets focalisés, chacun un seul job, tout
en conservant la spécificité LGC **multi-devise** (devises visibles + total EUR).

## Non-goals

- Pas de comptabilité complète (NG1) : le « Report à nouveau » est une **saisie**, pas un
  calcul de liasse. Le distribuable est indicatif.
- Pas de TVA (NG7). L'IS reste une **estimation** (NG2).

## Widgets (année civile 2026, réel + prévision)

### 1. Cashflow — entrées / sorties par mois
- Par mois : barre **Entrées** (empilée par devise, pleine) + barre **Sorties** (empilée par
  devise, hachurée). Mois futurs (après le mois courant) en **pâle** (prévision).
- Entrée = flux `revenue`; Sortie = flux `charge`. **Exclut** `transfer|conversion|investment`.
- KPI à droite : Total entrées (EUR), Total sorties (EUR), Solde net (EUR).
- Source : `pnl.monthly_pnl` (réel passé) + `forecast.project` (futur). Nouveau service
  `cashflow.monthly_cashflow(db, year, today)` qui fusionne les deux et renvoie par mois
  `{incoming_by_ccy, outgoing_by_ccy, incoming_eur, outgoing_eur, is_forecast}`.

### 2. Solde de trésorerie (ligne)
- Ligne = solde cumulé mensuel. **Part du vrai solde** (reconstruit `opening_balance +
  mouvements` sur le passé), projeté sur le futur via le forecast net. Pleine (réel) →
  pointillés (prévision). Menu « Tous les comptes ▾ » (filtre par compte, v2 — d'abord « tous »).
- Source : nouveau `treasury.balance_timeline(db, year, today)` → par mois
  `{month, balance_eur, is_forecast}`.

### 3. Profit & Loss (live) — style équation
- Étage 1 : `Revenus ⊖ Charges ⊜ Résultat ⊖ IS estimé ⊜ Résultat net`.
- Étage 2 : `Résultat net ⊕ Report à nouveau ⊜ Distribuable`.
- Table par devise dessous (revenus natif → EUR, charges EUR).
- Source : `pnl.monthly_pnl` (totaux + par devise) + `forecast.estimate_is` (IS).
  **Report à nouveau** : nouveau champ `Settings.retained_earnings_eur` (défaut 0), éditable
  dans Réglages. `pnl` (ou une fonction `pnl.summary`) renvoie
  `{revenue, charges, result, is_estimate, net_result, retained_earnings, distributable}`.

### 4. Invoice Timeline
- Barres empilées par mois : **Payé** (vert) / **Dû** (jaune) / **En retard** (rouge).
  - Payé = `status == 'paid'` (par mois d'émission).
  - Dû = `status != 'paid'` et `due_date >= today`.
  - En retard = `status != 'paid'` et `due_date < today`.
- Carte « Factures ouvertes » : liste des non-payées (devise native + badge statut).
- KPI : total « en attente » (EUR), nb factures ouvertes/en retard.
- Source : nouveau `invoices.timeline(db, today)` → `{months:[{month, paid_eur, due_eur,
  overdue_eur}], outstanding_eur, open:[...]}`.

## Data model change
- `Settings.retained_earnings_eur: Decimal = 0` (report à nouveau, éditable). Via `init_db`
  (dev), pas de migration Alembic (dette existante assumée).

## API (nouveaux endpoints, préfixe /api)
- `GET /api/dashboard/cashflow?year=` → cashflow mensuel.
- `GET /api/dashboard/balance-timeline?year=` → ligne de solde.
- `GET /api/dashboard/pnl-summary?year=` → équation P&L + distribuable.
- `GET /api/dashboard/invoice-timeline` → timeline factures.
- (ou regroupés sous un routeur `dashboard.py`.)

## Frontend
- `app/page.tsx` réécrit : KPI row + 4 cartes. Composants isolés :
  `components/dashboard/CashflowChart.tsx`, `BalanceChart.tsx`, `PnlWidget.tsx`,
  `InvoiceTimeline.tsx`. Palette LGC (CAD `#f59e0b`, EUR `#16a34a`, USD `#2563eb`;
  statut Payé/Dû/Retard = pos/jaune/neg). Un seul axe € par graphe (règle dataviz).
- `Réglages` : champ « Report à nouveau ».

## Testing
- Backend TDD par fonction : cashflow (split devise + forecast), balance_timeline (ancrage
  solde réel + projection), pnl summary (distribuable = net + report), invoice timeline
  (paid/due/overdue selon due_date vs today). `today` injectable partout.
- Front : tests de rendu par composant (jest) + `tsc`.
- Vérif live sur données réelles + screenshots.

## Ordre de build
1. `Settings.retained_earnings_eur` + Réglages.
2. Service+route `pnl-summary` (distribuable).
3. Service+route `cashflow`.
4. Service+route `balance-timeline`.
5. Service+route `invoice-timeline`.
6. Front : 4 composants + réécriture `page.tsx`.
7. Vérif live + screenshots.
