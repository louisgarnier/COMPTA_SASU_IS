# Product Requirements Document — LGC
> **Status:** `Locked` — 2026-07-01
> ⚠️ Une fois LOCKED, tout changement passe par un amendement daté en bas.
> Source de vérité. L'IA lit ce fichier avant chaque session.

---

## 1. Project Summary

| Field | Value |
|---|---|
| **Project name** | LGC |
| **One-liner** | Web app locale qui remplace l'Excel manuel de suivi cashflow d'une SASU en important les transactions bancaires via Open Banking pour piloter tréso, forecast et facturation sans ressaisie. |
| **Owner** | Louis Garnier |
| **Target completion** | MVP ~1–2 semaines |
| **Platform** | Web app **locale** (Mac), responsive (mobile-ready), portable cloud plus tard |
| **Tech stack** | Next.js + FastAPI (Python) + SQLite (via SQLAlchemy). Open Banking : Enable Banking. *(détails → `architecture.md`)* |

---

## 2. Goals & Non-Goals
> Cette section est LOI pour l'IA. Elle ne construit pas les non-goals.

### ✅ Goals (In Scope)
- **G1** — Importer automatiquement transactions **et** soldes de Revolut Business + Qonto via Enable Banking (synchro à la demande, bouton).
- **G2** — Catégoriser automatiquement chaque transaction par règles sur la contrepartie (règles **éditables**).
- **G3** — Calculer le CA en EUR avec le **FX réel**, en rattachant chaque crédit en devise (USD/CAD) à sa conversion Revolut correspondante.
- **G4** — Dashboard **tréso consolidée** : soldes bancaires + actifs manuels (crypto, bourse).
- **G5** — **P&L mensuel** en EUR (revenus vs charges par catégorie).
- **G6** — **Forecast cashflow** jusqu'à fin d'année, avec saisie éditable par mois (jours × TJH × fx, par client).
- **G7** — **Estimation d'IS** (15 % jusqu'à 42 500 €, 25 % au-delà), base éditable, clairement étiquetée « estimation ».
- **G8** — **Générer les factures** en PDF numéroté (devise USD/CAD, mentions légales), à partir de heures × TJH.
- **G9** — Marquer une facture **« payée » automatiquement** quand le virement correspondant est détecté en banque.
- **G10** — Fonctionner **en local, mono-utilisateur**, données sur le Mac ; UI responsive.
- **G11** — Suivre les **investissements** du compte pro (crypto, bourse, placements) : valeur d'ouverture (placements faits **avant l'année**), valeur courante datée, **gain/perte** calculé ; **gain net positif ajouté à la base imposable IS**.
- **G12** — Démarrer au **01/01/2026** : synchro des transactions à partir de cette date + **solde d'ouverture par compte au 01/01/2026** (saisie manuelle si non fourni par l'Open Banking).

### ❌ Non-Goals (Out of Scope — l'IA ne les construit pas)
- **NG1** — Logiciel comptable complet (pas de journal, grand livre, liasse fiscale) — ne remplace pas l'expert-comptable.
- **NG2** — Déclaration/télétransmission fiscale réelle — l'IS affiché est une **estimation**, pas une déclaration.
- **NG3** — Multi-utilisateur / fonctions d'équipe.
- **NG4** — Hébergement cloud / synchro automatique 24-7 — **reporté** (v1 = local + synchro manuelle).
- **NG5** — OCR de tickets/reçus de dépenses — les factures sont **générées** (sortantes), pas scannées. *(L'ancienne idée est explicitement abandonnée.)*
- **NG6** — Open Banking sur crypto/bourse — **saisie manuelle** uniquement.
- **NG7** — Gestion de TVA — SASU en **franchise en base** (art. 293 B), aucune TVA.
- **NG8** — Rapprochement FX 100 % automatique au-delà du lien conversion Revolut — un **lien manuel** de secours est acceptable.

---

## 3. User Stories

### Must Have (MVP)

| ID | Story | Acceptance Criteria |
|---|---|---|
| US-01 | En tant que dirigeant, je connecte Revolut Business et Qonto via Open Banking pour ne plus exporter à la main | - [ ] Connexion OAuth Enable Banking pour chaque banque <br>- [ ] Comptes (USD/CAD/EUR Revolut + EUR Qonto) listés après connexion <br>- [ ] Consentement 90 j géré + rappel de reconnexion |
| US-02 | Je clique « Synchroniser » et l'app récupère les dernières transactions + soldes | - [ ] Bouton lance un pull Enable Banking <br>- [ ] Nouvelles transactions insérées, doublons évités (`account_uid` + `external_id`) <br>- [ ] Soldes de chaque compte mis à jour <br>- [ ] Échec de synchro affiché clairement, jamais silencieux |
| US-03 | Chaque transaction est catégorisée automatiquement pour éviter le tri manuel | - [ ] Règles par contrepartie appliquées (URSSAF→charges sociales, AG2R→mutuelle, GoCardless→comptable, Free→télécom, DGFIP→impôts, outils SaaS, repas, transport, « Recharge par… »→revenu, conversion FX, virement interne) <br>- [ ] Inconnu → « à catégoriser » (jamais deviné en silence) <br>- [ ] Je peux corriger/créer une règle et re-catégoriser |
| US-04 | Mes revenus en USD/CAD sont convertis en EUR au taux réel | - [ ] Crédit entrant rattaché à sa conversion Revolut → montant EUR réel <br>- [ ] Si pas encore converti, taux du jour paramétrable utilisé (marqué « provisoire ») <br>- [ ] Lien manuel possible si rattachement auto échoue |
| US-05 | Je vois ma tréso consolidée à jour | - [ ] Solde par compte bancaire + total <br>- [ ] Ajout/maj manuel des actifs crypto & bourse (valeur + date) <br>- [ ] Total tréso global affiché |
| US-06 | Je vois mon P&L mensuel en EUR | - [ ] Revenus vs charges par catégorie, par mois <br>- [ ] Net mensuel + cumul annuel |
| US-07 | Je forecast mon cashflow jusqu'à fin d'année | - [ ] Saisie éditable par mois : jours travaillés + TJH par client + fx <br>- [ ] Revenu EUR projeté par mois <br>- [ ] Charges récurrentes projetées (moyenne des derniers mois) <br>- [ ] Tréso déroulée jusqu'à décembre |
| US-08 | J'ai une estimation de mon IS | - [ ] Base éditable (défaut ≈ revenus − charges) <br>- [ ] 15 % jusqu'à 42 500 €, 25 % au-delà <br>- [ ] Résultat étiqueté « estimation » |
| US-09 | Je génère une facture en PDF sans passer par Word | - [ ] Saisie : client, période, heures, TJH (devise auto selon client) <br>- [ ] Numéro auto qui continue la séquence (après la n°61) <br>- [ ] PDF conforme (mentions art. 293 B, SIRET, IBAN du bon compte devise) <br>- [ ] Date d'émission + échéance (+60 j) |
| US-10 | Mes factures passent « payée » toutes seules | - [ ] Statut draft → envoyée → payée <br>- [ ] Passe « payée » quand un crédit bancaire correspond (montant + devise + contrepartie) <br>- [ ] Encours visible (émises non payées, retards) |

### Should Have

| ID | Story | Acceptance Criteria |
|---|---|---|
| US-20 | J'exporte un récap (CSV/PDF) pour mon expert-comptable | - [ ] Export des transactions catégorisées sur une période <br>- [ ] Inclut le CA EUR et les charges |
| US-21 | J'ajoute une transaction manuelle (hors banque) | - [ ] Formulaire date/montant/devise/catégorie |

### Nice to Have (v2 — ne pas construire en v1)

| ID | Story | Notes |
|---|---|---|
| US-30 | Accès mobile hébergé (cloud) | Reporté — nécessite hébergement + auth |
| US-31 | Synchro bancaire automatique (webhook/planifiée) | Reporté — nécessite le cloud |
| US-32 | Envoi de la facture par email au client | Reporté |

---

## 4. Functional Requirements

- **FR-01** — Le système connecte Revolut Business et Qonto via Enable Banking (OAuth 2.0, JWT RS256).
- **FR-02** — Le système récupère à la demande transactions + soldes de tous les comptes connectés.
- **FR-03** — Le système déduplique les transactions par `(account_uid, external_id)`.
- **FR-04** — Le système catégorise chaque transaction via des règles éditables sur la contrepartie ; sinon `à catégoriser`.
- **FR-05** — Le système calcule `amount_eur` en rattachant les crédits USD/CAD à leur conversion Revolut ; à défaut, taux paramétrable marqué provisoire.
- **FR-06** — Le système affiche les soldes par compte et un total tréso incluant les actifs manuels (crypto, bourse).
- **FR-07** — Le système calcule un P&L mensuel EUR (revenus/charges par catégorie).
- **FR-08** — Le système projette revenus, charges et tréso par mois jusqu'à fin d'année à partir d'entrées éditables.
- **FR-09** — Le système estime l'IS : 15 % jusqu'à 42 500 €, 25 % au-delà, sur une base éditable ; résultat marqué « estimation ».
- **FR-10** — Le système génère un PDF de facture numéroté (séquence continue), devise selon le client, avec mentions légales et IBAN du compte de la devise.
- **FR-11** — Le système marque une facture « payée » quand un crédit bancaire correspond (montant + devise + contrepartie) ; sinon lien manuel.
- **FR-12** — Le système journalise chaque synchro et catégorisation avec issue (✅/❌) ; aucun échec silencieux.
- **FR-13** — Le système ne consigne jamais de données bancaires sensibles/PII en clair (IBAN masqués).
- **FR-14** — Le système ne synchronise que les transactions dont la date ≥ **2026-01-01** et stocke un **solde d'ouverture par compte au 2026-01-01** (éditable manuellement).
- **FR-15** — Le système suit chaque **investissement** (label, **devise**, valeur d'ouverture pré-année, apports de l'année, valeur courante datée — en devise native + équivalent EUR) et calcule le **gain/perte par devise** ; les valeurs d'ouverture pré-année s'ajoutent à la position de départ de leur devise ; les virements pro↔placement sont catégorisés `investment` (exclus du P&L d'exploitation).
- **FR-16** — L'estimation d'IS **ajoute le gain net positif des investissements** à la base imposable (une perte n'augmente pas la base).

---

## 5. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Une synchro des 2 banques se termine en < 30 s dans le cas nominal |
| NFR-02 | Reliability | Synchro idempotente : re-synchroniser ne crée pas de doublons ni ne corrompt les soldes |
| NFR-03 | Security | Aucun secret dans le code — tout via `.env` (App ID, clé RS256, etc.) |
| NFR-04 | Security | Données bancaires/PII jamais loguées en clair — IBAN masqués, IDs de transaction seulement |
| NFR-05 | Privacy | Données stockées **localement** (SQLite sur le Mac), pas d'envoi cloud en v1 |
| NFR-06 | Observability | Import, catégorisation, rapprochement facture : chaque opération loggée avec résultat |
| NFR-07 | Usability | UI pleinement utilisable sur navigateur mobile (responsive) |
| NFR-08 | Portability | Schéma DB portable SQLite → PostgreSQL sans réécriture applicative |

---

## 6. Data Requirements

| Dataset | Source | Format | Volume | Notes |
|---|---|---|---|---|
| Transactions bancaires | Enable Banking (Revolut Business, Qonto) | JSON → DB | ~30-60/mois | Multi-devises USD/CAD/EUR |
| Soldes de comptes | Enable Banking | JSON → DB | 4-5 comptes | Maj à chaque synchro |
| Conversions FX | Transactions Revolut | DB | ~qques/mois | Servent au calcul EUR réel |
| Factures | Générées par l'app | DB + PDF | ~4/mois (2 clients) | Numérotation continue |
| Clients | Config utilisateur | DB | 2 (SWIB, NWH) | Devise + TJH + IBAN par client |
| Actifs manuels | Saisie utilisateur | DB | crypto, bourse | Valeur + date de valorisation |
| Entrées forecast | Saisie utilisateur | DB | par mois/client | Jours, TJH, fx |
| Settings | Config utilisateur | DB | 1 | SIRET, TVA intracom, IBANs, barèmes IS, seed n° facture |

**Contraintes données :**
- Transactions importées non modifiées (seule la catégorie/le rattachement sont éditables applicativement).
- Montants et libellés bancaires jamais écrits dans les logs en clair.

---

## 7. Interfaces & Integrations

| System | Direction | Method | Auth |
|---|---|---|---|
| Enable Banking (Revolut Business) | Sortant (pull) | REST | JWT RS256 + OAuth 2.0 (.env) |
| Enable Banking (Qonto) | Sortant (pull) | REST | JWT RS256 + OAuth 2.0 (.env) |
| SQLite (local) | Read/Write | SQLAlchemy | fichier local |
| Génération PDF | Interne | lib Python (ex. WeasyPrint/ReportLab — à figer en archi) | — |

*(Abandonnés vs ancienne idée : Google Vision, Microsoft Graph/Outlook, Google Drive, Supabase — hors périmètre.)*

---

## 8. Error Handling Policy
- Toutes les erreurs sont attrapées et loggées — aucun échec silencieux.
- Échec de synchro bancaire → message clair à l'utilisateur, pas de crash, état précédent conservé.
- Rattachement FX impossible → transaction marquée « à rapprocher », lien manuel proposé.
- Transaction non reconnue → catégorie « à catégoriser », jamais devinée.
- Erreurs utilisateur affichées en clair, jamais de stack trace.

---

## 9. Constraints
- Mono-utilisateur, **local** — pas d'auth en v1 (l'app n'est pas exposée publiquement).
- Web app uniquement — pas de natif, pas d'Electron.
- Compte développeur Enable Banking requis (App ID + clé RS256).
- Franchise en base de TVA : aucun calcul de TVA.
- MVP visé : ~1–2 semaines.

---

## 10. Open Questions
> À trancher avant de passer en `Locked`.

| # | Question | Owner | Answer |
|---|---|---|---|
| Q1 | Nom définitif du projet ? | Louis | ✅ **LGC** |
| Q2 | Enable Banking couvre bien Revolut Business ET Qonto ? | Louis / à vérifier | *(à valider au 1er branchement)* |
| Q3 | Définition exacte de la base d'IS (CA vs bénéfice réel) ? | Louis / expert-comptable | ✅ IS sur le **résultat** (revenus − charges déduites) ; base éditable, règles exactes à caler avec l'expert-comptable |
| Q4 | Source de valorisation crypto/bourse (manuel simple ou saisie datée) ? | Louis | *(défaut : saisie manuelle datée)* |
| Q5 | Lib de génération PDF à figer (WeasyPrint vs ReportLab) ? | Décision archi | *(→ architecture.md)* |

---

## 📝 Amendments Log
| Date | Change | Reason |
|---|---|---|
| 2026-07-01 | Ajout G11/G12 + FR-14/15/16 : point de départ 01/01/2026 avec soldes d'ouverture manuels ; suivi des investissements (valeur d'ouverture pré-année, gain/perte) avec gain net positif imposé à l'IS | Précision métier apportée par Louis après lock : 2 types de flux (exploitation vs investissement) et ancrage de la tréso au 01/01/2026 |

---

## 📤 Outputs for 3-ARCHITECTURE.md
| PRD section | → Architecture input |
|---|---|
| Tech stack (§1) | Décisions de stack |
| FR (§4) | Découpage des composants |
| NFR (§5) | Perf & portabilité |
| Data (§6) | Modèle de données |
| Interfaces (§7) | Config services externes + seams |
| Error policy (§8) | Stratégie erreurs |
| Constraints (§9) | Limites du stack |
| User stories (§3) | Flux utilisateur |
