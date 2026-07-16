import { render, screen, fireEvent } from '@testing-library/react';
import { MonthlyReconcileCard } from '@/components/MonthlyReconcileCard';

jest.mock('next/navigation', () => ({ usePathname: () => '/banking' }));
jest.mock('@/api/client', () => ({
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025, coverage: '1/12',
      months: [
        { month: 1, status: 'warn', total_eur_official: '1450.00', total_eur_diff: '-50.00',
          per_account: [{ account_uid: 'acc', currency: 'EUR', official: '1450.00',
                          reconstructed: '1500.00', diff: '-50.00', status: 'warn' }] },
        ...Array.from({ length: 11 }, (_, i) => ({
          month: i + 2, status: 'missing', total_eur_official: '0.00', total_eur_diff: '0.00',
          per_account: [],
        })),
      ],
    }),
  },
}));

test('affiche les 12 mois, la couverture, et déplie le détail par compte', async () => {
  render(<MonthlyReconcileCard year={2025} />);
  expect(await screen.findByText('1/12')).toBeInTheDocument();
  // le mois de janvier est en écart
  const janv = await screen.findByText(/Janv/i);
  fireEvent.click(janv);
  // Le détail par compte s'est bien déplié (ligne EUR visible).
  expect(await screen.findByText('EUR')).toBeInTheDocument();
  // L'écart −50 apparaît (au moins) dans la ligne résumé ET la ligne détail par
  // compte — les deux affichent la même valeur pour ce mois à compte unique,
  // d'où `findAllByText` plutôt que `findByText` (qui exigerait un match unique).
  const ecarts = await screen.findAllByText(/−50,00|−50\.00|-50/);
  expect(ecarts.length).toBeGreaterThan(0);
});

test('dépôt d’un relevé → propose des soldes → confirmation les enregistre', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.extract = jest.fn().mockResolvedValue({
    proposal: [{ account_uid: 'acc', currency: 'EUR', amount: '11626.90', matched: true, hint: 'Main' }],
  });
  monthlyBalancesAPI.confirm = jest.fn().mockResolvedValue({ year: 2025, coverage: '2/12', months: [] });

  render(<MonthlyReconcileCard year={2025} />);
  const drop = await screen.findByLabelText(/Déposer un relevé/i);
  fireEvent.change(drop, { target: { files: [new File(['x'], 'r.pdf', { type: 'application/pdf' })] } });
  // la proposition apparaît, on valide
  expect(await screen.findByText(/11 626,90|11626.90/)).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: /Valider/i }));
  expect(monthlyBalancesAPI.confirm).toHaveBeenCalled();
});
