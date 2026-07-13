import { facturationYears } from '@/lib/years';

describe('facturationYears — sélecteur d\'exercices de la Facturation', () => {
  test('sans facture : descend un an sous l\'année précédente (factures N-2 payées en N-1)', () => {
    expect(facturationYears([], 2026)).toEqual([2024, 2025, 2026, 2027, 2028]);
  });

  test('la borne basse suit la plus ancienne facture (toujours un exercice de plus en arrière)', () => {
    expect(facturationYears(['2024-12', '2026-01'], 2026)).toEqual([2023, 2024, 2025, 2026, 2027, 2028]);
  });

  test('mois invalides ignorés', () => {
    expect(facturationYears(['', 'abcd-01'], 2026)).toEqual([2024, 2025, 2026, 2027, 2028]);
  });
});
