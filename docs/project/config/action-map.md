# Action Map — Blueprint des actions LGC (audit 2026-07-06)

> Source de vérité du comportement attendu de **chaque action de chaque module** + flux inter-modules.
> Établi par audit parallèle (9 agents, lecture seule : code + sondes API live).
> Légende état : ✅ marche · ⚠️ fonctionne mais trou/risque · ❌ cassé · 🚫 non implémenté / orphelin (endpoint sans UI, ou inverse).
> Sévérité : 🔴 haute · 🟠 moyenne · 🟡 basse.

## ⚠️ Contexte git (à traiter en premier)
Le working tree contient **beaucoup de travail non committé**, mélangé de deux sessions :
- Session précédente : **suppression de facture** (route DELETE + service + bouton UI + tests) — jamais committée, présente seulement dans le working tree, active sur le serveur live. Le « can't delete invoice » signalé était vrai **au dernier commit** ; le fix existe mais est **à risque** (perdu si `git checkout`).
- Session courante : fix création client (422/409) + feature reprice + fix… tout aussi non committé.
→ **Action : commiter proprement en lots cohérents** avant toute correction, pour repartir sur une base saine.

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
