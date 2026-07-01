# Epic Overview — LGC
> Généré via `5-EPICS.md` — 2026-07-01. Découpage en incréments livrables et testables.

| ID | Epic | But | Stories PRD | Status |
|---|---|---|---|---|
| EPIC-1 | Foundation & Scaffold | Squelette back+front qui tourne, base de données, logging, settings | (socle) | [ ] |
| EPIC-2 | Import bancaire (Open Banking) | Connexion Revolut Business + Qonto, synchro transactions + soldes | US-01, US-02 | [ ] |
| EPIC-3 | Catégorisation | Moteur de règles éditables, fallback « à catégoriser » | US-03 | [ ] |
| EPIC-4 | Tréso, FX & P&L | Rattachement FX→EUR, actifs manuels, tréso consolidée, P&L mensuel, dashboard | US-04, US-05, US-06 | [ ] |
| EPIC-5 | Forecast & IS | Projection mensuelle + estimation IS + écran forecast | US-07, US-08 | [ ] |
| EPIC-6 | Factures | Génération PDF numérotée + marquage payée auto | US-09, US-10 | [ ] |

**Ordre imposé par les dépendances :** 1 → 2 → 3 → 4 → 5, avec 6 (factures) qui peut démarrer après 2 (a besoin de la détection de virement pour le marquage payée).

**Reporté v1.1 / v2 :** US-20 (export comptable), US-21 (transaction manuelle), US-30/31/32 (cloud, synchro auto, envoi email).

---

## EPIC-1 — Foundation & Scaffold
| Story | Titre | Détail |
|---|---|---|
| S1.1 | Scaffold back + front | FastAPI (`/health`) + Next.js + script de lancement 1 commande |
| S1.2 | Couche base de données | SQLAlchemy + Alembic + SQLite ; toutes les entités (archi §4) ; montants en `Decimal` |
| S1.3 | Fondation logging | Loggers back/api/front, fichiers `logs/`, masquage IBAN/PII *(Step 4 méthodo)* |
| S1.4 | Settings | Entité + API + seed (société, SIRET, TVA, barèmes IS, seed n° facture = 62) |

## EPIC-2 — Import bancaire
| Story | Titre | Détail |
|---|---|---|
| S2.1 | Service Enable Banking (auth) | JWT RS256, `GET /aspsps` — **vérifie Revolut Business + Qonto** (résout Q2) |
| S2.2 | Flux de connexion OAuth | connect → sessions → stockage `bank_accounts` |
| S2.3 | Synchro | pull transactions **(date ≥ 2026-01-01)** + soldes, dédup `(account_uid, external_id)`, signe DBIT/CRDT |
| S2.4 | UI banque | Connexion banques + bouton « Synchroniser » + liste comptes/transactions |

## EPIC-3 — Catégorisation
| Story | Titre | Détail |
|---|---|---|
| S3.1 | Modèles catégories + règles | + seed des règles par défaut (URSSAF, AG2R, GoCardless, DGFIP, outils, repas…) |
| S3.2 | Moteur de catégorisation | applique règles, fallback « à catégoriser » |
| S3.3 | Application à la synchro + édition | re-catégo au sync + API d'édition manuelle |
| S3.4 | UI catégorisation | tri/correction transactions + éditeur de règles |

## EPIC-4 — Tréso, FX, Investissements & P&L
| Story | Titre | Détail |
|---|---|---|
| S4.1 | Rattachement FX → EUR | lier crédit devise ↔ conversion Revolut ; sinon taux provisoire + lien manuel |
| S4.2 | Soldes d'ouverture 01/01/2026 | solde par compte au point de départ (saisie manuelle, éditable) — ancre la tréso |
| S4.3 | Investissements | CRUD placements (crypto/bourse/…): **valeur d'ouverture pré-année** + apports + **valeur courante datée** → **gain/perte** ; virements pro↔placement en catégorie `investment` |
| S4.4 | Tréso consolidée | endpoint total (soldes comptes depuis l'ouverture + valeur courante des investissements) |
| S4.5 | P&L mensuel | revenus/charges d'**exploitation** par catégorie et par mois (investissements exclus) |
| S4.6 | UI Dashboard | tréso + P&L + investissements (gain/perte) + graphiques |

## EPIC-5 — Forecast & IS
| Story | Titre | Détail |
|---|---|---|
| S5.1 | Entrées forecast | modèle + API (jours/TJH/fx par mois/client) |
| S5.2 | Moteur de projection | revenus projetés + charges moyennes + déroulé tréso jusqu'à décembre |
| S5.3 | Estimation IS | 15 % / 25 % sur base éditable (résultat = revenus − charges **+ gain net positif des investissements**) |
| S5.4 | UI Forecast | écran de saisie + projection |

## EPIC-6 — Factures
| Story | Titre | Détail |
|---|---|---|
| S6.1 | Modèle facture + numérotation | séquence continue après n°61 |
| S6.2 | Génération PDF | template Jinja2 + WeasyPrint fidèle au Word (mentions art. 293 B, SIRET, IBAN par devise) |
| S6.3 | Marquage payée auto | rapprochement facture ↔ crédit bancaire au sync |
| S6.4 | UI Factures | création + liste + téléchargement PDF + statut/encours |
