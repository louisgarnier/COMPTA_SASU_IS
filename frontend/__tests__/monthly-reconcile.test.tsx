import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MonthlyReconcileCard } from '@/components/MonthlyReconcileCard';

jest.mock('next/navigation', () => ({ usePathname: () => '/banking' }));
jest.mock('@/api/client', () => ({
  balanceDocsAPI: {
    upload: jest.fn(),
    downloadUrl: (id: number) => `/api/balance-docs/${id}/download`,
  },
  monthlyBalancesAPI: {
    archiveUrl: (ids: number[]) => `/api/monthly-balances/docs-archive?ids=${ids.join(',')}`,
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025, coverage: '1/12',
      months: [
        { month: 1, status: 'warn', total_eur_official: '1450.00', total_eur_diff: '-50.00',
          per_account: [
            { account_uid: 'acc', currency: 'EUR', official: '1450.00',
              reconstructed: '1500.00', diff: '-50.00', status: 'warn' },
            { account_uid: 'acc-usd', currency: 'USD', official: '80381.99',
              reconstructed: '80400.00', diff: '-18.01', status: 'warn' },
          ],
          docs: [{ id: 7, name: 'Revolut', filename: 'statement-of-balances_31-Jan-2025.pdf' }] },
        ...Array.from({ length: 11 }, (_, i) => ({
          month: i + 2, status: 'missing', total_eur_official: '0.00', total_eur_diff: '0.00',
          per_account: [], docs: [],
        })),
      ],
    }),
  },
  openingsAPI: {
    get: jest.fn().mockResolvedValue({ year: 2026, accounts: [], tie_out: {} }),
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
  // Le compte USD doit être formaté en devise native ($US), pas en euros.
  expect(await screen.findByText(/80 381,99\s*\$US/)).toBeInTheDocument();
  expect(screen.queryByText(/80 381,99\s*€/)).not.toBeInTheDocument();
});

test('lien direct de téléchargement du relevé sur la ligne du mois', async () => {
  render(<MonthlyReconcileCard year={2025} />);
  const link = await screen.findByRole('link', { name: /Revolut/i });
  expect(link).toHaveAttribute('href', '/api/balance-docs/7/download');
});

test('cocher un mois affiche la barre d’action avec le nombre de relevés', async () => {
  render(<MonthlyReconcileCard year={2025} />);
  const cb = await screen.findByLabelText(/Sélectionner Janv 2025/i);
  fireEvent.click(cb);
  expect(await screen.findByText(/1 mois sélectionné/)).toBeInTheDocument();
  // 1 relevé lié à janvier → bouton "Télécharger les relevés (1)"
  expect(await screen.findByRole('button', { name: /Télécharger les relevés \(1\)/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Envoyer par mail/ })).toBeInTheDocument();
});

test('un sélecteur d’année permet de changer l’exercice affiché', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  render(<MonthlyReconcileCard year={2026} />);
  await screen.findByText('1/12');
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2026);

  fireEvent.click(await screen.findByRole('button', { name: '2025' }));
  await waitFor(() => expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2025));
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
  await waitFor(() => expect(monthlyBalancesAPI.confirm).toHaveBeenCalled());
});

test('dépôt d’un relevé → validation archive le PDF et lie son doc_id à la confirmation', async () => {
  const { monthlyBalancesAPI, balanceDocsAPI } = require('@/api/client');
  monthlyBalancesAPI.extract = jest.fn().mockResolvedValue({
    proposal: [{ account_uid: 'acc', currency: 'EUR', amount: '11626.90', matched: true, hint: 'Main' }],
  });
  monthlyBalancesAPI.confirm = jest.fn().mockResolvedValue({ year: 2025, coverage: '2/12', months: [] });
  balanceDocsAPI.upload = jest.fn().mockResolvedValue({ id: 42 });

  render(<MonthlyReconcileCard year={2025} />);
  const drop = await screen.findByLabelText(/Déposer un relevé/i);
  const file = new File(['x'], 'r.pdf', { type: 'application/pdf' });
  fireEvent.change(drop, { target: { files: [file] } });
  expect(await screen.findByText(/11 626,90|11626.90/)).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: /Valider/i }));

  await waitFor(() => expect(monthlyBalancesAPI.confirm).toHaveBeenCalled());
  expect(balanceDocsAPI.upload).toHaveBeenCalledWith(
    file,
    expect.objectContaining({ period_year: 2025, period_month: 12 }),
  );
  expect(monthlyBalancesAPI.confirm.mock.calls[0][3]).toBe(42);
});

test('décembre : la case « reporter en ouverture » apparaît et le report est transmis', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.extract = jest.fn().mockResolvedValue({
    proposal: [{ account_uid: 'acc', currency: 'EUR', amount: '11626.90', matched: true, hint: 'Main' }],
  });
  monthlyBalancesAPI.confirm = jest.fn().mockResolvedValue({ year: 2025, coverage: '12/12', months: [] });

  render(<MonthlyReconcileCard year={2025} />);
  // le mois par défaut de la carte est décembre (12)
  const drop = await screen.findByLabelText(/Déposer un relevé/i);
  fireEvent.change(drop, { target: { files: [new File(['x'], 'r.pdf', { type: 'application/pdf' })] } });
  await screen.findByText(/11 626,90|11626.90/);

  // la case de report est présente et cochée par défaut
  const carry = await screen.findByLabelText(/ouverture 2026/i);
  expect(carry).toBeChecked();

  fireEvent.click(await screen.findByRole('button', { name: /Valider/i }));
  await waitFor(() => expect(monthlyBalancesAPI.confirm).toHaveBeenCalled());
  // 5ᵉ argument = carryToOpening = true
  expect(monthlyBalancesAPI.confirm.mock.calls[0][4]).toBe(true);
});

test('novembre : pas de case de report', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.extract = jest.fn().mockResolvedValue({
    proposal: [{ account_uid: 'acc', currency: 'EUR', amount: '100.00', matched: true, hint: 'Main' }],
  });
  render(<MonthlyReconcileCard year={2025} />);
  // basculer le sélecteur de mois sur novembre
  fireEvent.change(await screen.findByLabelText(/Mois du relevé/i), { target: { value: '11' } });
  const drop = await screen.findByLabelText(/Déposer un relevé/i);
  fireEvent.change(drop, { target: { files: [new File(['x'], 'r.pdf', { type: 'application/pdf' })] } });
  await screen.findByText(/100,00|100.00/);
  expect(screen.queryByLabelText(/ouverture/i)).not.toBeInTheDocument();
});
