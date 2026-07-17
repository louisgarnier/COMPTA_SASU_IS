import type { ReactNode } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MonthlyReconcileView } from '@/components/dashboard/MonthlyReconcileView';

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock('@/api/client', () => ({
  balanceDocsAPI: { downloadUrl: (id: number) => `/api/balance-docs/${id}/download` },
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025,
      coverage: '4/12',
      months: [
        {
          month: 10, status: 'warn', total_eur_official: '121880.10', total_eur_diff: '-23.00',
          per_account: [{
            account_uid: 'acc-usd', currency: 'USD', official: '80381.99',
            reconstructed: '80400.00', diff: '-18.01', status: 'warn',
          }],
          docs: [{ id: 7, name: 'Revolut', filename: 'releve-oct.pdf' }],
        },
        {
          month: 12, status: 'ok', total_eur_official: '126493.91', total_eur_diff: '0.00',
          per_account: [], docs: [],
        },
      ],
    }),
  },
}));

test('affiche la couverture et le tableau des mois', async () => {
  render(<MonthlyReconcileView year={2025} />);
  expect(await screen.findByText('4/12')).toBeInTheDocument();
  expect(await screen.findByText(/Oct 2025/)).toBeInTheDocument();
  expect(await screen.findByText(/Déc 2025/)).toBeInTheDocument();
});

test('lecture seule : aucune case à cocher, aucun dépôt de relevé', async () => {
  render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Déposer un relevé/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Envoyer par mail/i })).not.toBeInTheDocument();
});

test('le lien « Déposer un relevé » pointe sur la carte de la page Banques', async () => {
  render(<MonthlyReconcileView year={2025} />);
  const link = await screen.findByRole('link', { name: /Déposer un relevé/i });
  expect(link).toHaveAttribute('href', '/banking#rappro-mensuel');
});

test('le sélecteur d’année recharge la vue', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2025);

  fireEvent.click(await screen.findByRole('button', { name: '2024' }));
  await waitFor(() => expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2024));
});

test('les montants par compte restent en devise native', async () => {
  render(<MonthlyReconcileView year={2025} />);
  fireEvent.click(await screen.findByText(/Oct 2025/));
  expect(await screen.findByText(/80 381,99\s*\$US/)).toBeInTheDocument();
  expect(screen.queryByText(/80 381,99\s*€/)).not.toBeInTheDocument();
});
