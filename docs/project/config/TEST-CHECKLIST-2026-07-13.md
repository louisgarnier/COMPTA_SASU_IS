# Liste de test utilisateur — état au 2026-07-13
> Tout est sur http://localhost:3001 (branche `import-csv-2025`). Audit complet passé, 4 bloquants corrigés le jour même, 270 tests back + 29 front verts. Coche au fur et à mesure ; note tout écart.

## 1. Dashboard (page d'accueil)
- [ ] **Sélecteur d'année** : passe sur 2025 → badge « IR », IS estimé = 0, chiffres non vides ; reviens sur 2026 → régime IS, distribuable 302 473,80
- [ ] **Cran Réalisé / Engagé / Prévisionnel** : les widgets P&L, cashflow, courbe et Distributions changent ; le RAN suit le cran
- [ ] **Widget P&L** : l'équation Revenus − Charges = Résultat − IS = Net tombe juste au centime
- [ ] **Widget Cashflow** : bascule « Année en cours » ↔ « Année fiscale » ; toggle sorties non-op ; sur 2025 les mois sont vivants (import CSV)
- [ ] **Courbe de trésorerie** : 2026 finit sur le vrai solde (KPI) ; **2025 montre la vraie trajectoire** (jan ~136 217 → juin ~62 920 → déc ~121 309) — c'était plat avant le fix du jour
- [ ] **Pont de trésorerie** : ouverture + banque + résiduel ; clique une ligne → arrive sur Transactions filtrées ; au 31/12/2025 le résiduel est ~−498 € SANS warning
- [ ] **Factures ouvertes / timeline** : mention « 6 derniers mois glissants » visible sous le titre

## 2. Transactions
- [ ] Les **928 transactions 2025** sont là (filtre par dates) avec la colonne banque d'origine (badge Qonto violet / Revolut bleu)
- [ ] **Export CSV** : exercice 2025 → fichier de 928 lignes ; 2026 → 334
- [ ] Filtres : type, « À catégoriser » (758 en 2025 — c'est ta prochaine tâche de catégorisation), recherche texte
- [ ] Catégorise une transaction 2025 à la main → relance une synchro bancaire → **ta catégorie doit survivre**
- [ ] Catégorise l'iPhone 16 (673 €, avril) et le MacBook Pro (1 313 €, avril) en **« Immobilisation »** → ils sortent des charges P&L mais restent visibles en sorties non-op du cashflow

## 3. Banques
- [ ] Carte **Import CSV** : re-glisse un de tes fichiers → la prévisualisation doit afficher 0 importable / tout en doublons (idempotence) — n'importe pas
- [ ] Après chaque synchro : un fichier `lgc_*_sync.db` apparaît dans `data/backups/`
- [ ] Justificatifs de solde (📎) s'ouvre

## 4. Réglages
- [ ] **Soldes d'ouverture** : le sélecteur propose 2025 ET 2026 ; les ouvertures 2025 sont remplies (Qonto 315,48 · Revolut EUR 121 406,31 · USD 21 160…) avec tie-out vert ; le champ année accepte n'importe quelle année
- [ ] is_start_year=2026, report à nouveau 166 200, alerte tréso basse (mets un seuil > solde pour voir le bandeau, puis remets 0)

## 5. Factures / Facturation
- [ ] Onglet Heures & jours : année 2025 accessible, création d'une facture dans le passé (émission directe « due »)
- [ ] Ouvre une facture → PDF (anglais, nom `Invoice_Mois_Année_CODE_LG.pdf`) avec ton bloc bancaire client
- [ ] Aging : les 3 factures dues affichent leur retard ; marque une facture « envoyée »
- [ ] Essaie de passer une facture en « payée » à la main → refus (409) — seul le rapprochement paie

## 6. Placements
- [ ] « Bourse direct » : gain attendu 76 700 → visible dans P&L prévisionnel (+6 700) et la courbe converge à l'échéance (déc)
- [ ] Le toggle « + placements » sur la courbe
- [ ] ⚠️ Donnée à corriger par toi : le placement « xrp » saisi à la main (9 000 USD) vs la vraie tx importée (8 971,21 USD) — ajuste le montant puis rapproche-le de la transaction du 01/10/2025

## Après tes tests — prochaine phase (rapprochement comptable 2025)
1. Catégoriser les 758 tx 2025 (règles + manuel)
2. Saisir les factures clients 2025 (dont la CAD JPSB 5 580) et les rapprocher
3. Onglet État financier : compte de résultat + vue de rapprochement vs bilan du comptable (à construire — maquette d'abord)
