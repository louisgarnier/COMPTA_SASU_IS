# Spec — Séparer « revenu gagné » (accrual) et « cash encaissé » (cash) — P&L vs Cashflow vs Trésorerie

Date : 2026-07-03
Statut : validé (design), en implémentation
Contexte : SASU de conseil payée à ~45 jours. Le mois travaillé, le mois de
facturation et le mois d'encaissement diffèrent. Chaque module doit lire la
bonne date, sinon P&L, cashflow et estimation IS sont faux.

## Problème

Aujourd'hui `pnl.py` **et** `cashflow.py` s'appuient sur `Transaction.booked_date`
(la date où le cash touche la banque) :

- Le **P&L** est donc un P&L « encaissement » : un revenu de janvier payé en mars
  tombe en mars → résultat décalé de ~45j et **IS de fin d'exercice faux** (une
  facture de décembre payée en février bascule dans la mauvaise année).
- Le **cashflow prévisionnel** bucketise les factures `forecast` sur leur `month`
  de **service** → il suppose « service janvier = cash janvier », alors qu'à 45j
  c'est du cash de mars.

## Principe directeur

Un euro porte plusieurs dates ; chaque module lit **la sienne** :

| Date facture | Sens | Module qui la lit |
|---|---|---|
| `month` / `period_*` | mois travaillé (service) | **P&L / IS** (accrual) |
| `issue_date` | date d'émission | (numérotation, timeline) |
| `due_date` = issue + `payment_terms_days` | cash **attendu** | **Cashflow** (futur) |
| `paid_date` / `booked_date` | cash **arrivé** | Trésorerie, cashflow (réel) |

Cashflow & Trésorerie parlent « quand l'argent bouge ». P&L parle « quand le
revenu est gagné ». Un écart de ~45j entre les deux vues est **normal et attendu**.

## Décisions (validées avec l'utilisateur)

- **D1 — P&L en comptabilité d'engagement (accrual).** Revenu = factures émises.
- **D2 — Rattachement du revenu au mois travaillé** (`Invoice.month`), pas au mois
  de paiement ni d'émission.
- **D3 — Hybride assumé :** revenu en accrual (depuis les factures), **charges en
  cash** (`booked_date`). Pas de module facture fournisseur (NG5) ; sur une SASU
  tout le décalage de timing est sur le revenu.

## Comportement cible par module

### Trésorerie (`treasury.py`) — inchangé
Solde réel synchronisé (courant) / reconstruction opening+mouvements (historique).
Déjà correct (EPIC-4). Aucune modification.

### P&L (`pnl.py`) — passe en accrual
- **Revenu** = factures `status ∈ {due, paid}` rattachées à leur **mois de service**
  (`Invoice.month`). Montant EUR par facture :
  - `paid` → `amount_eur_received` (FX réel encaissé) si présent ;
  - sinon `amount_eur_forecast` (FX théorique) si > 0 ;
  - sinon conversion théorique du natif `amount` (taux Réglages).
- **Filet anti-perte (revenus non facturés)** : les transactions de revenu **non
  rattachées à une facture** (`invoice_id IS NULL`) comptent toujours comme revenu,
  par `booked_date` (cash), pour ne pas perdre un encaissement divers. Une
  transaction **rattachée** (`invoice_id` renseigné) est **exclue** (la facture la
  compte déjà) → pas de double comptage.
- **Charges** = inchangé (transactions de catégorie `charge`, par `booked_date`).
- Les factures `forecast` (non émises) sont **hors P&L** (projection, pas revenu
  réalisé). Elles restent dans la projection IS via `forecast.project()`.

### Cashflow (`cashflow.py`) — le futur bucketise sur la date d'encaissement
- **Passé + mois en cours** = RÉEL : transactions par `booked_date`. Inchangé.
- **Mois futurs** = encaissements ATTENDUS depuis les factures **non payées**
  (`status ∈ {forecast, due}`), bucketisés sur la **date de paiement attendue** :
  - facture `due` (émise) → `due_date` ;
  - facture `forecast` (non émise) → dernier jour du mois de service +
    `client.payment_terms_days` (émission supposée en fin de mois travaillé).
  - Montant EUR : `amount_eur_forecast` si > 0, sinon conversion théorique du natif.
  - Devise du bucket = devise du client.
- Les factures `paid` sont exclues du futur (leur cash est déjà dans le réel).
- **Sorties** (charges prévisionnelles) : inchangé (moyenne / prorata via
  `forecast.project()`).

### Fiabiliser `due_date` (`invoices.py`)
`create_invoice` crée une facture `due` mais **ne pose pas `due_date`**. On ajoute
`due_date = issue_date + client.payment_terms_days` (comme `generate_invoice`),
sinon le cashflow ne sait pas quand l'encaisser.

### Rapprochement auto au sync (`banking.py`)
`sync` catégorise mais n'appelle pas `reconcile_payments`. Tant que le paiement
n'est pas rapproché, la transaction a `invoice_id NULL` → double comptage avec la
facture émise dans le P&L. On ajoute `reconcile_payments(db)` en fin de `sync`
(après la re-catégorisation) pour fermer la boucle automatiquement.

## Points ouverts / limites assumées (documentées)
- **Fenêtre de double comptage** : entre l'import d'un paiement et son
  rapprochement. Fermée par le `reconcile_payments` auto au sync ; se corrige au
  sync suivant si un match a échoué.
- **Encaissements attendus en retard** (facture `due` dont `due_date` est déjà
  passée mais non payée) : non réinjectés dans le mois courant du cashflow (les
  mois réels ne montrent que les mouvements bancaires réels). Visibles dans la
  timeline factures (`outstanding_eur`). Refinement futur possible.
- **Revenu accru non facturé** (mois travaillé écoulé resté en `forecast`) : non
  compté au P&L (seules les factures émises comptent). Le flux normal émet la
  facture pour un mois travaillé, donc peu impactant.

## Fichiers touchés
- `backend/services/pnl.py` — revenu accrual + filet non-facturé.
- `backend/services/cashflow.py` — encaissements attendus par date de paiement.
- `backend/services/invoices.py` — `create_invoice` pose `due_date`.
- `backend/services/banking.py` — `reconcile_payments` auto au sync.
- Tests : `test_treasury_pnl.py`, `test_dashboard_cashflow.py` (+ cas accrual /
  date de paiement / due_date / reconcile-au-sync).

## Critères d'acceptation
1. Une facture `due` mois de service `2026-01`, `due_date 2026-03` : apparaît dans
   le **P&L de janvier** et dans le **cashflow de mars** (pas l'inverse).
2. Sans aucune facture, le P&L reste identique (filet non-facturé = cash) → pas de
   régression sur les exercices importés sans facturation dans l'app.
3. Un paiement importé et rapproché n'est **pas** compté deux fois (facture +
   transaction) dans le P&L.
4. `create_invoice` produit une facture avec `due_date` cohérente.
5. Tous les tests back verts (`make test` back).
