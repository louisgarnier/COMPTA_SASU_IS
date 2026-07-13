# Action Map — Blueprint des actions LGC (audit 2026-07-06)

> Source de vérité du comportement attendu de **chaque action de chaque module** + flux inter-modules.
> Établi par audit parallèle (9 agents, lecture seule : code + sondes API live).
> Légende état : ✅ marche · ⚠️ fonctionne mais trou/risque · ❌ cassé · 🚫 non implémenté / orphelin (endpoint sans UI, ou inverse).
> Sévérité : 🔴 haute · 🟠 moyenne · 🟡 basse.

## ✅ Corrigé le 2026-07-06 (12 commits, base git propre)
Tous les points 🔴 **haute priorité** + une partie du 🟠 moyen sont réglés, testés et committés :
- **Transactions** : filtre Type (kind dérivé de la catégorie) · filtre « À catégoriser » (fourre-tout ∪ NULL) ✅
- **FX** : ajout de devise + validation taux>0 + devise ajoutée persistante ✅
- **Placements** : écran complet créé (nav + page + résumé + CRUD, EUR via FX) ✅
- **Dashboard** : ligne de solde futur alignée sur le cashflow (encaissements factures) ✅
- **Banques** : sync isolée par compte (savepoint) + déconnexion + statut honnête + compteurs complets ✅
- **Factures** : suppression committée (route+UI+tests) ✅
- **Validation/UX** : erreurs 422 lisibles · champs numériques vides omis · validation Réglages (IS∈[0,1], SIRET, capital≥0) · colonnes FX mortes retirées ✅
- **Catégories** : suppression (FK-safe) · ré-appliquer les règles à l'historique · édition motif/priorité ✅
- **Forecast** : charges année future (repli 12 mois) · trésorerie de départ réelle · bascule TJM/THM re-price ✅

## ✅ Backlog moyen + bas — traité le 2026-07-06 (session 2)
Tous les points 🟠 restants + les 🟡 utiles sont réglés, testés et committés :
- **Forecast** : ✕ « vider une prévision » (DELETE `/api/forecast/{client}/{month}`, ne touche pas une facture émise) · champ **note** par prévision câblé de bout en bout ✅
- **Factures** : statut `paid` **réservé au rapprochement** (PATCH refuse `paid` → 409) · enum de statut validé (`Literal`, 422 sinon) · `changeStatus` (code mort) retiré · **compteur rendu** à la suppression du dernier n° émis (pas de trou) · hint « n° de départ » en Réglages ✅
- **Transactions** : champ **recherche texte** (description + contrepartie, client-side) ✅
- **Dashboard** : **sélecteur d'année** (widgets dynamiques) · « + Nouvelle facture » câblé → `/invoices` · bouton mort « Tous les comptes ▾ » retiré ✅
- **Banques** : **sélection des comptes à la connexion** (échange code → aperçu → rattachement des cochés) · **vérif `state` OAuth** anti-CSRF (émis à connect, consommé au callback, rejeu refusé) ✅
- **Clients** : test de suppression **204** (sans facture) + **409** (facture liée) ✅

Verif finale : backend **156 passed**, frontend **17 passed**, `tsc` clean.

**Restant (assumé, non prioritaire)** : KPI « Trésorerie totale » vs « Solde banques » gardés volontairement (diffèrent dès qu'il y a des placements) · solde passé inclut transferts (cosmétique) · Transactions création manuelle + lien FX manuel (🟡 bas) · endpoints orphelins GET client/{id}, PDF WeasyPrint (choix produit).

---

## 🔴 Backlog priorisé (synthèse cross-modules)

### 🔴 Haute
1. **FX — conversion 1:1 silencieuse.** Une devise utilisée sans taux (GBP live) retombe à `rate=1` sans erreur → **fausse tréso/P&L/IS/cashflow**. Impossible d'ajouter une devise tant qu'aucune transaction ne l'utilise. `services/fx.py:40` (fallback `_ONE`), `services/fx.py:70-86` (rates_view limité aux devises en usage). → bloquer/alerter + champ « ajouter devise ».
2. **Transactions — filtre Type toujours vide.** `Transaction.kind` n'est **jamais assigné** (default `'other'`) → 321/321 tx en `'other'` → filtres revenu/charge/… = 0. `models.py:167` + catégorisation qui ne pose que `category_id`. → dériver `kind` de la catégorie.
3. **Transactions — filtre « À catégoriser » vide.** La catégorisation range les tx dans la catégorie fourre-tout (id 13) au lieu de laisser `category_id NULL` ; le filtre cherche `IS NULL` → 0. `categorize.py:113-124` vs `transactions.py:91-92`. → laisser NULL ou filtrer sur la catégorie fourre-tout.
4. **Placements — module sans UI.** Backend CRUD complet + `investmentsAPI` défini, **aucune page ni lien nav** → impossible de saisir un placement ; la base IS omet les plus-values latentes. `Nav.tsx:7-14`, pas de `app/investments`. → créer l'écran Placements.
5. **Banques — sync sans gestion d'erreur + statut trompeur.** Consentement expiré → 401 → 500 qui **avorte tout le sync** ; badge « Connecté » ne teste que la présence des creds, pas la validité du consentement 90j ; re-consentement fragile (redirect ngrok mort, pas de route `/banking/callback`). `banking.py:510` (pas de try/except), `banking.py:87-115` (statut). → try/except par compte + statut = santé session + fiabiliser le callback.
6. **Commiter la suppression de facture** (+ ses tests) — feature déjà écrite, non committée, à sécuriser.
7. **Dashboard — solde futur incohérent avec le cashflow.** La ligne de solde ignore les encaissements de factures attendus (source `forecast_inputs` vide) alors que le cashflow les compte → solde de fin d'année **sous-estimé de ~57 960 €**. `treasury.py:214` vs `cashflow.py:112`. → partager la même source d'encaissements attendus.

### 🟠 Moyenne
- **Erreurs 422 affichées « [object Object] »** (Clients + Réglages) : `client.ts:21` ne gère pas `detail` en tableau ; `save()` envoie `''` pour les champs numériques vides → 422 pydantic. Motif **répété** → fix générique dans le client API + omettre les champs vides.
- **Catégories** : édition de catégorie orpheline (endpoint sans UI) ; pas de suppression de catégorie ; édition de règle partielle (seuls `enabled`/`category_id`) ; **`recategorize_all` non exposé** → les règles ne s'appliquent à l'historique qu'à la prochaine sync.
- **Forecast** : pas de suppression/remise à zéro d'une cellule (vider n'efface pas la facture forecast) ; `starting_cash_eur` jamais transmis (cumul tréso démarre à 0) ; bascule TJM/THM qui ne re-price pas ; charges=0 pour une année entièrement future (IS surévalué) ; champ `note` mort.
- **Factures** : `changeStatus` = code mort ; pas de « Marquer payé » manuel (seul le rapprochement clôt) ; `PATCH status` sans validation d'enum ; compteur non décrémenté à la suppression (numérotation à trous).
- **Banques** : pas de déconnexion/suppression de compte ; `SyncOut` tronque les compteurs catégorisés/rapprochés ; pas de sélection de comptes.
- **Réglages** : `default_fx_usd/cad` = colonnes mortes (double source FX) ; aucune validation (taux IS ∈ [0,1], FX>0, SIRET) ; save qui casse si un champ numérique est vidé.
- **Clients** : suppression non testée (204 + 409).

### 🟡 Basse
- Transactions : pas de recherche texte ; pas de création manuelle ; lien FX manuel sans UI.
- Catégories : pas de réordonnancement ni de test de règle.
- Clients : `GET /api/clients/{id}` orphelin.
- Factures : endpoints WeasyPrint PDF/download orphelins (choix : page imprimable).

---

## Détail par module

### Transactions
| Action | UI | Endpoint | Attendu | État | Sév. |
|---|---|---|---|---|---|
| Lister | page.tsx:105 | GET /api/transactions | 321 lignes date desc | ✅ | — |
| Filtre catégorie (id) | page.tsx:163 | ?category_id= | filtre | ✅ | — |
| Filtre « À catégoriser » | page.tsx:169 | ?uncategorized=true | non catégorisées | ❌ (0 vs 82) | 🔴 |
| Filtre Type (kind) | page.tsx:180 | ?kind= | filtre nature | ❌ (tout 'other') | 🔴 |
| Filtre dates | page.tsx:196 | ?date_from/to | borne | ✅ | — |
| Catégoriser inline | page.tsx:266 | PATCH /{id} | pose category_id | ⚠️ à vérifier live | 🟡 |
| Synchroniser | page.tsx:146 | POST /banking/sync | import+recat | ⚠️ | 🟡 |
| Recherche texte | absent | absent | filtrer mot-clé | 🚫 | 🟠 |

### Catégories
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| Lister cat./règles | page.tsx:97 | GET categories / category-rules | ✅ | — |
| Créer catégorie | page.tsx:226 | POST /categories | ✅ | — |
| Éditer catégorie | **absent** | PATCH /categories/{id} existe | 🚫 orphelin | 🟠 |
| Supprimer catégorie | absent | absent | 🚫 | 🟠 |
| Créer/activer/supprimer règle | page.tsx:286/294/373 | POST/PATCH/DELETE category-rules | ✅ | — |
| Éditer motif/priorité règle | absent | PATCH accepte | ⚠️ partiel | 🟠 |
| Ré-appliquer règles | absent | non exposé (interne sync) | ❌ | 🟠 |

### Forecast
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| Charger / changer année | page.tsx:111/242 | GET /forecast | ✅ | — |
| Saisir jours/heures/taux (liés) | page.tsx:466/476/488 | PUT /forecast | ✅ | — |
| Enregistrer grille | page.tsx:227 | PUT /forecast | ✅ | — |
| Supprimer/vider une prévision | absent | (upsert ignore driver≤0) | ❌ | 🟠 |
| Note par prévision | absent | PUT accepte note | ❌ mort | 🟡 |
| Trésorerie de départ | jamais passée | starting_cash_eur | ⚠️ cumul à 0 | 🟠 |
| Bascule TJM/THM | page.tsx:433 | PATCH client | ⚠️ pas de reprice | 🟠 |
| Charges année future | — | project | ⚠️ =0 → IS faux | 🟠 |

### Clients
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| CRUD complet | page.tsx | GET/POST/PATCH/DELETE /clients | ✅ | — |
| Reprice preview/apply/annuler | page.tsx:117/344/341 | reprice endpoints | ✅ | — |
| Erreur 422 (champ numérique vide) | — | — | ⚠️ « [object Object] » | 🟠 |
| Suppression testée | — | DELETE | ⚠️ non testée | 🟠 |
| GET /clients/{id} | absent | existe | 🚫 orphelin | 🟡 |

### Factures
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| Lister / générer / imprimer | page.tsx:244/253 | GET, POST /generate, GET /print | ✅ | — |
| Rapprocher / annuler rappr. | page.tsx:269/262 | candidates/reconcile/unreconcile | ✅ | — |
| **Supprimer** | page.tsx:278 | DELETE /{id} | ⚠️ **non committé** | 🔴 |
| Marquer payé manuel | absent | (PATCH status back) | ❌ | 🟠 |
| changeStatus | défini non branché | PATCH | 🚫 code mort | 🟠 |
| PATCH status validation enum | — | — | ⚠️ absente | 🟠 |
| PDF/download WeasyPrint | absent | POST /pdf, GET /download | 🚫 orphelin | 🟡 |

### Banques
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| Statut / ASPSP / comptes | page.tsx | GET status/aspsps/connections | ✅ (statut trompeur) | 🔴 |
| Connexion OAuth / coller code | page.tsx:178/215 | POST connect/sessions | ⚠️ fragile (ngrok mort) | 🔴 |
| Synchroniser | page.tsx:125 | POST /sync | ⚠️ pas de gestion erreur | 🔴 |
| Déconnecter un compte | absent | absent | ❌ | 🟠 |
| Compteurs sync (catég./rappr.) | — | SyncOut tronque | ⚠️ | 🟠 |

### Réglages
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| Charger / enregistrer société+IS+facturation | page.tsx:31/55 | GET/PUT /settings | ✅ | — |
| Éditer/enregistrer taux FX | FxRatesCard.tsx | GET/PUT /fx-rates | ✅ | — |
| Ajouter une devise FX | absent | (PUT accepte) | 🚫 | 🟠 |
| default_fx_usd/cad | absent | Settings (mort) | ❌ colonnes mortes | 🟠 |
| Validation (IS, FX>0, SIRET) | — | — | ⚠️ absente | 🟠 |
| Save si champ numérique vidé | page.tsx:37 | PUT | ⚠️ 422 | 🟠 |

### Placements / FX
| Action | UI | Endpoint | État | Sév. |
|---|---|---|---|---|
| CRUD placements + résumé | **AUCUN** | GET/POST/PATCH/DELETE/summary manual-assets | 🚫 backend orphelin | 🔴 |
| Taux FX (list/save) | FxRatesCard | GET/PUT /fx-rates | ✅ | — |

### Dashboard
| Élément | Widget | Endpoint | État | Sév. |
|---|---|---|---|---|
| KPI tréso / résultat / IS / factures | page.tsx:70-74 | treasury, pnl-summary, invoice-timeline | ✅ (chiffres croisés cohérents) | — |
| KPI « Solde banques » vs « Tréso totale » | page.tsx:70-71 | treasury | ⚠️ doublon si placements=0 | 🟡 |
| CashflowChart (réel/prévision) | CashflowChart.tsx | cashflow | ✅ | — |
| Ligne de solde (passé + futur) | BalanceChart.tsx | balance-timeline | ⚠️ **ignore encaissements factures** | 🟠 |
| PnlWidget / InvoiceTimeline | PnlWidget/InvoiceTimeline.tsx | pnl, invoice-timeline | ✅ | — |
| Bouton « Tous les comptes ▾ » | BalanceChart.tsx:48 | — | 🚫 mort | 🟠 |
| Bouton « + Nouvelle facture » | InvoiceTimeline.tsx:88 | — | 🚫 mort (pas de nav) | 🟠 |
| Sélecteur d'année | page.tsx:16 | — | ❌ figé 2026 (désync 2027) | 🟡 |

**Incohérence majeure** : ligne de solde futur (`treasury.py:214` via `forecast.project` → source `forecast_inputs` vide) vs cashflow futur (`cashflow.py:112` via factures ouvertes) → **le solde de fin d'année sous-estime de ~57 960 €** les encaissements de factures. Les deux widgets racontent deux futurs incompatibles. 🟠
**Autres** : cashflow futur creux (entrées=0 sauf mois avec facture) ; solde passé inclut transferts/conversions (relief, cosmétique) ; endpoint `balance-docs` orphelin du dashboard.

---

## Flux inter-modules (carte)
- **FX (fx_rates) → TOUT calcul EUR** : forecast, pnl, treasury, cashflow, invoices. ⚠️ fallback 1:1 silencieux si devise sans taux.
- **Transactions ↔ Catégories** : catégorisation auto par règles à la sync ; édition inline. ⚠️ fourre-tout vs NULL ; règles non ré-applicables hors sync.
- **Forecast → Facture** : prévision = facture `forecast` → génération `forecast→due`. ✅
- **Client → Forecast (reprice)** : taux/mode → recalcul prévisions futures. ✅ (câblé seulement page Clients, pas Forecast).
- **Facture ↔ Transaction (rapprochement)** : reconcile/unreconcile/delete libèrent `tx.invoice_id`. ✅
- **Client ↔ Factures** : delete client bloqué 409 si factures liées. ✅
- **Banque (sync) → Transactions → Catégories → Factures (rapprochement)** : chaîne d'import. ⚠️ pas de gestion d'erreur.
- **Placements → base IS** : plus-values latentes positives → base imposable. ⚠️ branché mais aucune UI pour saisir.
- **Réglages → génération facture** (compteur), **→ IS/distribuable** (barème, report à nouveau). ✅

---

# Audit 2026-07-13 — features livrées depuis le 6/07 (6 agents, lecture seule, sondes GET live)

> Périmètre : tout ce qui a été livré entre le 7/07 et le 13/07 (Lots A/B/C, placements, régime IR→IS, cross-year, facturation, backup, import CSV 2025). Base auditée : branche `import-csv-2025` avec les 928 tx 2025 importées. **Les 4 bloquants trouvés ont été corrigés le jour même** (voir « Corrigé le 2026-07-13 »).

## ✅ Corrigé le 2026-07-13 (suite à l'audit)
- 🔴 **Catégorie « Immobilisation » absente de la base réelle** — le seed ne tournait que sur table vide ; désormais backfill idempotent par nom à chaque démarrage (catégories système manquantes recréées, lignes existantes jamais touchées). Catégorie id 30 présente en base live.
- 🔴 **Courbe / soldes à date / pont 2025 plats** (les 928 tx 2025 ignorées) — double cause : (a) aucune `OpeningBalance` 2025 → **ouvertures 2025 saisies** (dérivées par identité : ouverture 2026 − net 2025 par compte, cohérentes bilan + chaînage CSV 861/861), pont 2025 : résiduel −498 € (au lieu d'un faux +139 844 €) ; (b) plancher legacy `opening_balance_date` dans `_bank_movements_eur` → fix `since=after` (le rebours depuis le solde actuel ne masque plus les mouvements pré-ancre), courbe 2025 = 12 valeurs réelles distinctes, écart rebours↔ancre = 22,17 € (résidu Revolut connu).
- 🟠 **Réglages : ouvertures d'exercice impossibles pour une année passée** (bouton = max+1 seulement) → champ année libre.
- 🟠 **Courbe « + placements » : saut potentiel à l'échéance** si valeur actuelle ≠ remboursement attendu → `expected_value_eur ?? current_value_eur` au mois de bascule (aligné sur le cash injecté côté banque).
- 🟡 Invoice Timeline : mention « 6 derniers mois glissants (indépendant de l'année sélectionnée) » ajoutée (le widget ignore le sélecteur d'année par design).

## État par module (nouvelles features depuis le 6/07)
- **Dashboard** : sélecteur d'année (N-1 accessible, badge IR pré-IS) ✅ · sélecteur Réalisé/Engagé/Prévisionnel (RAN suit le cran) ✅ · widget P&L (équation exacte au centime live, produits financiers attendus/réalisés) ✅ · widget Cashflow (année civile vs fiscale, toggle non-op, overflow N+1) ✅ · courbe tréso (toggle + placements, cross-year) ✅ · pont de trésorerie + clic → Vue tréso ✅ · Distributions & IS ✅ · factures ouvertes ≈ EUR + timeline EUR réel ✅ · alertes tréso basse / factures exercice antérieur ✅ (inactives sur les données actuelles, logique vérifiée)
- **Transactions** : banque d'origine ✅ · export CSV par exercice ✅ (2025 : 928 lignes, 2026 : 334) · filtres kind/à-catégoriser/recherche/vue-tréso ✅ · non-régression recatégorisation manuelle ✅ (test dédié) · lien FX manuel 🔗 ✅ (câblage, 16 crédits candidats)
- **Factures/Facturation** : Heures & jours (année 2025, facture dans le passé, n° éditable) ✅ · PDF WeasyPrint V1.1 + anglais + nom de fichier ✅ (503 propre sans pango) · bloc bancaire/adresse/mention légale par client ✅ · aging ✅ · sent_date ✅ · machine à états verrouillée ✅ · suppression + compteur rendu ✅
- **Banques/Réglages** : backup fail-closed avant sync ✅ · import CSV 3 étapes ✅ (865+63 réelles importées, idempotence prouvée) · sélection de comptes + anti-CSRF state ✅ · BalanceDocsModal ✅ · ouvertures par exercice (année libre depuis ce jour) ✅ · is_start_year/RAN/alerte tréso/FX tous consommés en aval ✅
- **Placements/Forecast** : latent non taxé, gains attendus (+6 700 exactement dans la base IS forecast) et réalisés ✅ · remboursement = entrée non-op ✅ · charges projetées signées (ERR-005) ✅ · vider/note/TJM-THM ✅ · P&L annuel imprimable (2025 et 2026 sans crash) ✅
- **Transversal** : IR→IS tient avec les vraies données 2025 (IS=0, RAN 2026 inchangé : 166 200 → distribuable 302 473,80 exact) ✅ · allocation FX contrainte par date ✅ · sweep santé : toutes les routes GET 200, < 1 s (balance-timeline 0,24 s à 1 262 tx) ✅ · logs du jour : zéro vraie erreur ✅

## ⚠️ Restes connus (non bloquants, par sévérité)
1. 🟠 Pas de pagination sur GET /api/transactions + N+1 sur catégorie (41-81 ms à 1 262 tx — dette d'échelle, pas d'impact actuel)
2. 🟡 `?year=` ignoré silencieusement sur GET /api/transactions et /api/invoices (filtres année = client-side ; seul /export a year)
3. 🟡 `kind='other'` partagé immobilisation/non-catégorisé (filtrer par catégorie, pas par kind) ; immobilisation absente de l'overlay fiscal cashflow (`_fiscal_nonop_flows`)
4. 🟡 2 branches 409 non testées (re-reconcile paid, unreconcile non-paid — code correct lu) ; POST /api/invoices (orphelin UI) ne calcule pas amount_eur_forecast
5. 🟡 `invoice_filename_suffix` absent du formulaire Réglages ; tranches aging 30/60 j en dur (front) ; seuil résiduel pont 2 % en dur ; logging manquant sur le catch large des routes import ; écart ~213 € entre CA forecast.project et pnl.summary(forecast) (2 chemins de calcul, à verrouiller par test croisé)
6. ℹ️ Données (pas du code) : 758/928 tx 2025 « À catégoriser » (≈ −193 k€ hors P&L tant que non catégorisé) · placement #2 « xrp » saisi à la main (9 000 USD) ≠ tx réelle importée (8 971,21 USD, id 475) — à rapprocher · features placements non exerçables visuellement tant qu'aucun placement actif (câblage vérifié par code)
