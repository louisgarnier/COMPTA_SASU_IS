# Cycle de vie des factures (forecast → due → paid) — Design

**Date:** 2026-07-03
**Status:** Architecture approuvée (Option A — fusion). Build story par story.
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
3. **Forecast grille** — saisie prévisionnelle client × mois (jours→heures→montant). ⟵ *prochaine*
4. **Génération PDF** — au format des .docx (numéro, dates, IBAN de réception par devise, mentions légales).
5. **Rapprochement** — match transaction↔facture, FX réel, variance forecast/réel.

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
