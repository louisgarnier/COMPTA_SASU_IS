# Cycle de vie des factures (forecast → due → paid) — Design

**Date:** 2026-07-03
**Status:** ✅ Implémenté (Option A — fusion). Toutes les stories ①–⑤ terminées (2026-07-03).
**Epic:** EPIC-5 (facturation)

## Vision
Un seul objet **facture** parcourt un cycle de statut :
`forecast` (mois à venir, planifiée) → `due` (générée + envoyée, pas payée) → `paid` (paiement reçu et rapproché).
Le forecast de CA **est** une facture prévisionnelle (on fusionne l'ancien `forecast_inputs`).

## Principe anti-doublon (contrainte dure)
Pour un couple **client × mois**, le Cashflow / la tréso comptent le revenu depuis **une seule source** :
- facture `paid` → la **transaction réelle** rapprochée (`paid_transaction_id`).
- facture `forecast`/`due` non payée → le **montant prévisionnel**.
- **jamais les deux.** La transaction payée est liée à la facture, donc pas recomptée en revenu générique.

## Modèle de données (cible)
`Invoice` (fusion de forecast_inputs) :
- `status`: `forecast | due | paid` (remplace draft|sent|paid)
- `client_id`, `month` ('YYYY-MM')
- `days`, `hours_per_day` → `hours`, `rate` (taux horaire), `currency`
- `amount` (= hours × rate, devise) ; `amount_eur_forecast` (au taux théorique)
- `number`, `issue_date`, `due_date` (posés à la génération)
- `paid_transaction_id`, `paid_date`, `amount_received` (natif), `fx_rate`, `amount_eur_received`
- `variance_eur` = amount_eur_received − amount_eur_forecast
- `pdf_path`
Facturation **à l'heure** (cf .docx réels : « 152 hours @ 120 $/h »), TVA 293B, délai 60 j.

## Roadmap (stories, une spec/plan chacune si besoin)
1. **Client card** — enrichir `Client`, UI CRUD. ✅ *fait (commit 6e273a9)*
2. **Cycle de vie** — migration `forecast_inputs`→`Invoice`, statut, règle anti-doublon dans cashflow/treasury. ✅ *fait (ADR-007, 100 tests backend)*
3. **Forecast grille** — saisie prévisionnelle client × mois (jours→heures→montant). ✅ *fait (TJM/THM, année, N clients ; maquette v6)*
4. **Génération PDF** — au format des .docx (numéro, dates, IBAN client, mentions légales). ✅ *fait (page imprimable, template fidèle)*
5. **Rapprochement** — match transaction↔facture, FX réel, variance forecast/réel. ⟵ *prochaine*

---

## Story ① — Client card (cette itération)

**But :** gérer les clients avec toutes les infos nécessaires à la facturation et à l'envoi.

**Champs `Client` (ajouts en gras) :**
| Champ | Rôle |
|---|---|
| `code`, `legal_name` | identité (déjà là) |
| `address`, **`country`** | adresse d'envoi sur la facture |
| **`contact_name`**, **`email`** | destinataire de l'envoi |
| `currency` | devise de facturation (déjà là) |
| `tjh` | taux horaire par défaut (déjà là) |
| **`default_hours_per_day`** (défaut 8) | dérive heures = jours × h/j (forecast) |
| **`payment_terms_days`** (défaut 60) | calcule `due_date = issue_date + N j` |
| `counterparty_match` | rapprochement auto (déjà là) |
| `pay_iban` | *(existant ; les IBAN de RÉCEPTION par devise iront plutôt en Réglages — story ④)* |

**Non-goals de la story :** génération, forecast, rapprochement (stories suivantes). Les IBAN de réception (tiens, par devise) sont traités en story ④.

**Backend :** ajout des colonnes (`init_db` + ALTER sur `data/lgc.db`), Pydantic `ClientOut`/`ClientIn` dans `routes/clients.py`, CRUD déjà présent (list/create/update) + ajouter `delete` si absent. TDD.

**Frontend :** page **Clients** (liste + formulaire create/edit) au style LGC (comme la page Réglages). Ajout au menu latéral. Suit le pattern form existant.

**Tests :** backend (create/update avec nouveaux champs, defaults), front (rendu liste + form).

---

## Story ③ — Grille Forecast (facturation horaire + TJM/THM) — maquette validée v6

**But :** saisir les prévisions de CA par client × mois, en **facturation au jour (TJM)** ou **à l'heure (THM)**, pour toute année (2026, 2027, …).

**Décisions de design (maquette v6 approuvée) :**
- **Une table par client**, tous affichés ; un client créé sur la page Clients apparaît ici avec ses défauts. Bouton « + Ajouter un client » → page Clients (source unique, pas de double saisie).
- **Sélecteur d'année** (segmenté, 2026/2027/2028/+). **Mois dynamiques** : année future = 12 mois ; année en cours = mois écoulés grisés (le réel prime), saisie dès le mois courant ; année passée = lecture seule.
- **Mode de facturation par client** (`billing_mode` ∈ `tjm | thm`, mémorisé sur la fiche client, basculable depuis l'en-tête de la table) :
  - **TJM** (jour) : **Jours** éditable (décimales, ex. 16,5), **Heures 🔒** = jours × h/j, **Taux $/jour**, **Montant = jours × taux**.
  - **THM** (heure) : **Jours ⇅ Heures tous deux éditables et liés** (saisir l'un recalcule l'autre via h/j), **Taux $/heure**, **Montant = heures × taux**.
- **Lignes par table** : Jours → Heures → Taux → **Montant (devise locale)** `[facture]` → **€** (conversion). Colonne **Total** à droite.
- **Montant devise locale** = ce qui s'imprime sur la facture (ex. « 6 h @ 120 $/h = 720 $ »). **€** = montant × **FX théorique** (Réglages, ADR-006 ; plus de saisie FX manuelle par cellule).
- KPI en tête (CA projeté / charges / base IS / IS estimé) pour l'année sélectionnée.

**Modèle de données :**
- `Client.billing_mode` (String, défaut `tjm`) — nouveau champ (ALTER live + page Clients).
- `Client.tjh` reste le taux par défaut (interprété $/jour en TJM, $/heure en THM).
- `Invoice` (forecast) porte déjà `days`, `hours_per_day`, `hours`, `rate`, `amount`, `fx_rate_forecast`, `amount_eur_forecast`. Ajout `rate_unit` (String `day|hour`) pour reproduire le montant sans ambiguïté. `amount = days×rate` (day) ou `hours×rate` (hour) ; `amount_eur_forecast = amount × fx(devise client, théorique)`.

**Contrat API (route `/api/forecast`) — évolution :**
- `ForecastInputIn/Out` : `month, client_id, days, hours, rate, rate_unit, note` (le `fx_rate` manuel disparaît ; le FX vient de `fx_rates` par devise client).
- `year` déjà paramétrable (`?year=`) ; le front pilote les mois affichés selon année vs today.
- `upsert_inputs` calcule `hours`/`days` complémentaires via `client.default_hours_per_day`, `amount` selon `rate_unit`, `amount_eur_forecast` via FX théorique de la devise client.

**Backend :** MAJ `services/forecast.py` (upsert/get + `ForecastRow` enrichi `hours`, `rate_unit`), `routes/forecast.py` (modèles Pydantic), `Client.billing_mode` + `Invoice.rate_unit` (models + ALTER), page Clients (champ mode). TDD.

**Frontend :** réécriture `app/forecast/page.tsx` — sélecteur d'année, N tables clients, bascule TJM/THM par client, saisie liée jours⇄heures (THM), lignes dérivées (montant/€), colonne Total, mois dynamiques. E2E via webapp-testing.

**Non-goals :** génération PDF (④), rapprochement/variance UI (⑤).
