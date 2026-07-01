# Brainstorm — LGC
> Output of Stage 1 (`docs/project/requirements/1-BRAINSTORM.md`)
> Status: **GO** — 2026-07-01

---

## 0. Freeform Input

### Raw Thoughts
Automatiser mon fichier Excel « forecast cashflow LGC 2026 » qui suit la compta/tréso de ma SASU
(LGC, à l'IS). Aujourd'hui je fais tout à la main : j'exporte les transactions de Revolut Business
et de Qonto, je les colle dans Excel, je catégorise chaque ligne (charges / facturation /
conversion FX), je calcule mon CA en EUR avec le taux de change réel, je suis ma tréso multi-comptes,
je forecast les mois restants et j'estime l'IS. Je veux connecter mes banques (Revolut Business +
Qonto) via l'Open Banking pour récupérer transactions et soldes automatiquement, et que l'app
génère aussi mes factures (fini Word et les updates manuelles source d'erreurs).

### Notes & Context
- SASU LGC, consultant IT (NAF 6202A), Grenoble. Franchise en base de TVA (art. 293 B CGI). Régime IS.
- 2 clients facturés mensuellement : **SWIB** (120 USD/h) et **NWH** (180 CAD/h), ~8h/j, ~17-21 j/mois.
- Payé ~50 jours après émission, via Revolut Business (comptes USD / CAD / EUR).
- Devises converties en EUR sur Revolut ; **Qonto** = compte EUR pour charges récurrentes
  (URSSAF, mutuelle AG2R, expert-comptable via GoCardless, Free Mobile, impôts DGFIP…).
- Fichiers de référence dans `docs/project/requirements/` : `forecast cashflow LGC 2026.xlsx`
  (4 onglets : summary / Factu / revolut / Sheet4=Qonto) + 4 factures `.docx` (Jan/Feb, NWH/SWIB).

---

## 1. The One-Liner

**LGC Compta** est une **web app locale** qui remplace mon Excel manuel en important
automatiquement les transactions de ma SASU via l'Open Banking, pour piloter tréso, forecast et
facturation sans ressaisie.

---

## 2. The Problem

- **Who has this problem?** Moi (dirigeant de SASU à l'IS), et beaucoup de consultants/freelances
  multi-devises qui pilotent leur boîte sans logiciel comptable lourd.
- **How are they solving it today?** Export bancaire manuel → copier-coller dans Excel →
  catégorisation et calculs FX à la main → factures tapées dans Word.
- **Why is the current solution inadequate?** Chronophage, répétitif, et **source d'erreurs**
  (FX, numérotation de factures, oublis de lignes). Ne donne pas de vue temps réel.
- **How often does this problem occur?** Chaque mois (clôture, facturation) et à chaque fois que je
  veux savoir où j'en suis en tréso.

---

## 3. The Solution

### Core Workflow (User's Journey)
1. Je clique **« Synchroniser »** → l'app récupère via Open Banking les transactions + soldes
   Revolut Business et Qonto.
2. L'app **catégorise automatiquement** chaque transaction (charges, revenus, conversion FX,
   virements internes) et calcule le CA en EUR avec le FX réel.
3. Je consulte un **dashboard** : tréso consolidée (banques + crypto/bourse en saisie manuelle),
   P&L mensuel, **forecast** jusqu'à fin d'année et **estimation d'IS**.
4. Je **génère mes factures** (PDF numéroté, bonne devise et mentions légales) ; l'app les marque
   **« payée »** automatiquement quand le virement correspondant arrive.

### What Makes This Different
Ultra-ciblé sur le besoin réel d'un dirigeant de SASU multi-devises : pas un logiciel comptable à
mille fonctions, juste l'automatisation exacte de mon Excel + la génération de factures. Local,
privé, gratuit, et pensé pour un accès mobile ultérieur.

---

## 4. Assumptions & Risks

| Assumption | Risk if Wrong | Mitigation |
|---|---|---|
| Enable Banking couvre Revolut Business **et** Qonto | Une banque non connectable → import cassé | Vérifier au 1er branchement ; fallback import CSV |
| Les conversions FX Revolut se rattachent au crédit entrant pour le vrai montant EUR | CA EUR faux | Rapprochement auto + **lien manuel** en secours |
| Consentement Open Banking 90 j acceptable | Friction de reconnexion | Rappel de reconnexion dans l'app |
| Numérotation de factures reprise après la n°61 sans doublon | Numéros en conflit | Compteur seedé dans `settings`, contrôle d'unicité |
| Crypto & bourse en **saisie manuelle** (hors Open Banking) | Tréso incomplète si oubli | Champ dédié + date de valorisation |
| Local mono-utilisateur suffit pour la v1 (accès mobile = plus tard) | Besoin cloud anticipé | Archi portable SQLite→Postgres dès le départ |

---

## 5. Feasibility Check

- **Technical complexity:** Medium-High (intégration Open Banking + rapprochement FX = les seams à risque)
- **Time estimate (MVP):** ~1–2 semaines (4 piliers + intégration bancaire ; le « 1 semaine » initial est optimiste)
- **Dependencies / blockers:** Compte développeur Enable Banking (App ID + clé RS256) ; comptes Revolut Business & Qonto connectables
- **Skills gap:** Aucun bloquant (stack Python/Next.js maîtrisée ; blueprint Enable Banking déjà dans le repo)
- **Maintenance burden:** Low (mono-utilisateur, local ; reconnexion bancaire trimestrielle)

---

## 6. Go / No-Go Decision

**Success criteria:**
- Minimum (MVP done): synchro auto des 2 banques + tréso/P&L EUR à jour + génération de factures + marquage payée auto
- Full success: forecast fiable jusqu'à décembre + estimation IS, plus jamais besoin d'ouvrir l'Excel ni Word
- Failure looks like: une banque ne se connecte pas, le FX EUR est faux, ou toutes les transactions ne sont pas rapprochées

**Decision:** **[x] GO** — le problème est réel et récurrent, la solution est cadrée, je m'engage.

**Rationale:** C'est une corvée mensuelle chronophage et risquée que j'assume déjà manuellement ;
l'automatiser me fait gagner du temps et fiabilise ma compta.

---

## 📤 Approach retenue (pour l'archi)

Web app **locale**, responsive (mobile-ready), portable cloud plus tard :
**Next.js (front) + FastAPI/Python (calculs FX, forecast, PDF) + SQLite**.
Synchro **à la demande** (bouton, pas de webhook en local) via **Enable Banking**.

---

## 📤 Next Steps

_→ GO validé. Proceed to `docs/project/requirements/2-PRD.md` → `config/prd.md`._
