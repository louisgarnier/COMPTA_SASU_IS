# Rapprochement mensuel officiel — Design (Étape 1)

> Statut : **proposé** · Date : 2026-07-16 · Épic : EPIC-8
> Sous-projet #1 des évolutions LGC (« Ajout docs officiels — transactions et soldes Qonto/Revolut »).

## 1. Contexte & problème

Aujourd'hui LGC vérifie les soldes officiels **une fois par an** (`opening_balances` :
un solde de clôture par compte et par exercice, avec un tie-out annuel). Une dérive
— typiquement un **frais FX mal capturé ou manquant** par la synchro — n'apparaît
qu'en fin d'année, sans localisation.

L'utilisateur dispose, par exercice, des **relevés officiels mensuels** :
- **Revolut « Relevé des soldes »** (12/an) : à une date de fin de mois, liste le
  solde réglé de **tous les comptes/poches** (Main EUR/USD/GBP, USD, Louis CAD, XRP,
  Hedging…).
- **Relevés mensuels Qonto** (12/an) + **CSV Qonto** (colonne `Solde` = solde courant
  après chaque opération).
- **transaction-statement annuel Revolut** + CSV Qonto : les transactions officielles
  de l'année (contiennent chaque jambe de conversion FX et chaque ligne de frais).

Fichiers réels : `docs/Doc_comptable/2025/` (gitignoré — PII).

## 2. Objectif (Étape 1)

Un **rapprochement mensuel** : pour chaque compte et chaque mois, confronter le
**solde officiel de fin de mois** (extrait des relevés) au **solde reconstitué par
l'app** (ancre d'ouverture + Σ mouvements jusqu'à la fin du mois), avec un badge
✅/⚠️, et **archiver le relevé PDF** comme preuve.

Bénéfice : une dérive (ex. frais FX manquant) se voit **au mois où elle apparaît**,
sur le **compte** concerné, et **de combien**.

### Non-objectifs (Étape 1)
- Pas de réconciliation ligne-à-ligne des transactions (c'est l'**Étape 2**, §11).
- Pas d'import/écrasement des transactions synchronisées (elles restent la source
  des mouvements ; les relevés servent d'**ancre de contrôle**, pas de remplacement).
- Pas de gestion TVA (NG7). Pas de 2023-2024 (hors périmètre).

## 3. Données d'entrée (structure réelle observée)

**Revolut « Relevé des soldes »** (`statement-of-balances_31-Dec-2025.pdf`) — texte
extractible proprement. Par compte : nom (`Main`, `Hedging`, `USD`, `Louis CAD`, `XRP`…),
`Devise`, `IBAN` (parfois), `Solde réglé` (ex. `€11 626.90`, `$80 381.99`,
`5 580.00 CAD`, `3 000.000000` XRP). En-tête : « Informations en date du 31 décembre 2025 ».

**CSV Qonto** (`;`-séparé) : colonnes `Date de la valeur (local)`, `Montant total (TTC)`,
`Débit`, `Crédit`, **`Solde`**, `Devise`, `Nom du compte`, `IBAN du compte`, … Le solde
de fin de mois = `Solde` de la dernière opération du mois.

## 4. Modèle de données

Montants en `Decimal`. Auto-migration via `_ensure_columns` (colonnes nullable) + une
nouvelle table.

### 4.1 Nouvelle table `monthly_balances`
Un solde officiel de fin de mois, par compte.
```
id            INTEGER PK
account_uid   VARCHAR  NOT NULL  (FK logique bank_accounts.account_uid)
year          INTEGER  NOT NULL
month         INTEGER  NOT NULL  (1..12)
balance       NUMERIC(18,6)      # natif ; 6 décimales pour XRP & co
currency      VARCHAR  NOT NULL
source_doc_id INTEGER  NULL      (FK balance_documents.id — la preuve)
confirmed_at  DATETIME NULL      # validé par l'utilisateur (hybride)
updated_at    DATETIME
UNIQUE(account_uid, year, month)
```

### 4.2 Extension `BalanceDocument` (table existante)
Ajouter le rattachement à une **période** (le relevé Revolut couvre tous les comptes à
une date → niveau mois ; le relevé Qonto → compte+mois) :
```
period_year   INTEGER NULL
period_month  INTEGER NULL      # NULL = pièce d'exercice (bilan, grand livre…)
```
`account_uid` reste nullable (déjà le cas) : NULL = pièce multi-comptes ou globale.

### 4.3 `opening_balances` (inchangée)
Reste l'ancre annuelle. La reconstruction mensuelle part de l'ancre d'ouverture de
l'exercice (`openings.opening_anchor`) et ajoute les mouvements jusqu'à fin de mois.

## 5. Extraction (hybride : extraire → confirmer → archiver)

Nouveau module `backend/services/statement_extract.py`.

- **`extract_revolut_balances(pdf_bytes) -> {"as_of": date, "balances": [{name, currency, iban_last4, amount}]}`**
  Parse le texte du « Relevé des soldes » (blocs `Devise` / `Solde réglé`). Robuste aux
  espaces insécables (séparateur FR) et aux symboles `€ $ £ CAD XRP`.
- **`extract_qonto_month_end(csv_text, year, month) -> [{account_iban, currency, balance}]`**
  Dernière valeur `Solde` du mois par compte.
- **Mapping relevé → compte** : clé `(devise, 4 derniers IBAN)` quand l'IBAN est présent,
  sinon `(devise, nom normalisé)`. Comptes cibles réels : Qonto EUR `d48f510a`, Revolut
  Main EUR `cd56227f` (…527), Hedging EUR `656b0ee1` (sans IBAN), Main USD `4746d577`
  (…527), USD `97bbafb4` (…484), CAD `e5c9b482`, GBP `ba846d1f`. XRP → non bancaire
  (poche/`Investment`), affiché mais hors tie-out € bancaire.
- **Confirmation** : l'extraction renvoie une **proposition** (jamais écrite d'office) ;
  l'UI l'affiche, l'utilisateur corrige/valide, PUIS on écrit `monthly_balances`
  (`confirmed_at` posé) + archive le PDF (`period_year/month`).

## 6. Rapprochement (tie-out mensuel)

Nouveau service `backend/services/monthly_reconcile.py`, réutilise la logique de
`openings.py` (ancre + Σ mouvements) mais bornée à `fin de mois`.

- `reconstruct_balance(db, account_uid, year, month) -> Decimal` : ancre d'ouverture de
  l'exercice + Σ mouvements natifs `booked_date ≤ dernier jour du mois`.
- `monthly_reconciliation(db, year) -> {months:[{month, per_account:[{account_uid,
  currency, official, reconstructed, diff, status}], total_eur_official, total_eur_diff,
  status, docs:[...] }], coverage: "11/12"}`. `status = ok` si `|diff| < 0.01` (natif),
  sinon `warn`. Conversion € via `fx.to_eur` pour les totaux.
- Un mois sans `monthly_balances` saisi → `status = "missing"` (badge gris).

## 7. API — `backend/api/routes/monthly_balances.py` (prefix `/api/monthly-balances`)

- `POST /extract` (multipart : `file`, `provider`) → renvoie la **proposition**
  extraite (soldes + as_of + mapping proposé), sans rien écrire.
- `PUT  /?year=&month=` (body : liste `{account_uid, balance}` validés + `doc_id?`) →
  upsert `monthly_balances` + pose `confirmed_at`.
- `GET  /reconciliation?year=` → la vue §6 (12 mois, tie-out, couverture, docs liés).
- Archivage : réutilise `POST /api/balance-docs` (déjà existant) enrichi de
  `period_year/period_month` ; le `doc_id` retourné est passé au `PUT`.

## 8. UI (page Banques — carte dédiée)

Maquette approuvée : `.superpowers/brainstorm/.../rappro-mensuel-v2.html`.
- **Bandeau ingestion** : dropzone « Déposer un relevé » + compteur `X/12 mois`.
  Rappel BAU : « à refaire chaque mois, ou 12 d'un coup pour rattraper ».
- **Tableau 12 mois** : `Fin de mois · Solde officiel (€) · Écart · Statut (✅/⚠️/gris) ·
  Relevés (📎)`. Ligne **dépliable** → détail par compte (officiel / reconstitué / écart).
- **Modale de confirmation** post-dépôt : soldes extraits éditables → « Valider ».
- Composants : nouveau `MonthlyReconcileCard.tsx` ; réutilise `BalanceDocsModal`
  (enrichi période). Client `frontend/src/api/client.ts` : `monthlyBalancesAPI`.
- Charte : Tailwind, accent `#0052cc`, en-tête gris `#f4f5f7`, badges vert/ambre,
  montants `Decimal` alignés à droite, devise par compte.

## 9. Sécurité / PII

- Les relevés contiennent IBAN/soldes → PII. Stockage local uniquement
  (`data/balance_docs/`, déjà gitignoré via `data/`). `docs/Doc_comptable/` doit être
  **ajouté au `.gitignore`** (comme `docs/docs2025/`, `docs/20232024/`).
- Aucun log de solde/IBAN complet (conventions logging du projet).
- Backup fail-closed (ADR-008) avant tout upsert de masse (rattrapage 12 mois).

## 10. Tests (TDD)

Backend :
- `test_statement_extract.py` : parse d'un « Relevé des soldes » réel (fixture texte
  anonymisée) → soldes attendus par compte ; parse Qonto month-end depuis CSV.
- `test_monthly_reconcile.py` : reconstruction fin de mois = ancre + Σ mouvements ;
  `status ok/warn/missing` ; **régression frais manquant** : retirer une tx de frais →
  le mois passe `warn` avec l'écart exact.
- `test_monthly_balances_api.py` : `/extract` n'écrit rien ; `PUT` upsert + `confirmed_at` ;
  `/reconciliation` couverture + totaux €.
Front :
- `MonthlyReconcileCard.test.tsx` : rendu 12 mois, dépliage détail, badge missing,
  flux dépôt→confirmation (mock API).

## 11. Étape 2 — conditionnelle (esquisse, hors périmètre immédiat)

Déclenchée seulement si l'Étape 1 révèle des écarts. Sur un mois ⚠️, drill-down qui
compare les **transactions officielles** du mois (transaction-statement Revolut annuel
+ CSV Qonto) aux transactions synchronisées, repère la **ligne de frais FX manquante**,
et la comptabilise (catégorie « Frais bancaires ») → l'écart retombe à 0. Spec séparée
le moment venu.

## 12. Points ouverts

- **XRP / non-bancaire** : affiché comme solde officiel (preuve) mais exclu du tie-out
  € bancaire (c'est un `Investment`). À confirmer à l'implémentation.
- **Hedging EUR sans IBAN** : mapping par nom (`Hedging`) faute d'IBAN — vérifier qu'il
  n'entre pas en collision avec Main EUR.
- **Robustesse parsing** : si un futur relevé change de format, l'extraction doit
  **échouer proprement** (proposition vide + message), jamais écrire de valeur fausse —
  d'où l'étape de confirmation obligatoire.
```
