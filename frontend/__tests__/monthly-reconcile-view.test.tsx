import type { ReactNode } from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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

test('un changement de la prop year (pilotée par le sélecteur global) recharge la vue', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  const { rerender } = render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2025);

  rerender(<MonthlyReconcileView year={2024} />);
  await waitFor(() => expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalledWith(2024));
});

test('les montants par compte restent en devise native', async () => {
  render(<MonthlyReconcileView year={2025} />);
  fireEvent.click(await screen.findByText(/Oct 2025/));
  expect(await screen.findByText(/80 381,99\s*\$US/)).toBeInTheDocument();
  expect(screen.queryByText(/80 381,99\s*€/)).not.toBeInTheDocument();
});

test('une réponse tardive après changement d’année n’écrase pas la sélection courante (race condition)', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  let resolve2025: (v: unknown) => void = () => {};
  let resolve2024: (v: unknown) => void = () => {};
  monthlyBalancesAPI.reconciliation
    .mockImplementationOnce(() => new Promise((r) => { resolve2025 = r; }))
    .mockImplementationOnce(() => new Promise((r) => { resolve2024 = r; }));

  const { rerender } = render(<MonthlyReconcileView year={2025} />);
  rerender(<MonthlyReconcileView year={2024} />);

  // La réponse 2024 arrive en premier (rapide) ; on flushe explicitement via
  // act() pour être sûr que l'état a bien été committé avant d'enchaîner.
  await act(async () => {
    resolve2024({ year: 2024, coverage: '2/12', months: [] });
    await Promise.resolve();
  });
  expect(screen.getByText('2/12')).toBeInTheDocument();

  // La réponse 2025, lancée avant mais arrivée après, est désormais obsolète :
  // elle ne doit pas écraser l'affichage de 2024.
  await act(async () => {
    resolve2025({ year: 2025, coverage: '4/12', months: [] });
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(screen.getByText('2/12')).toBeInTheDocument();
  expect(screen.queryByText('4/12')).not.toBeInTheDocument();
});

test('affiche une erreur réseau au lieu de rester bloqué sur « Chargement… »', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.reconciliation.mockRejectedValueOnce(new Error('Erreur réseau'));

  render(<MonthlyReconcileView year={2025} />);
  expect(await screen.findByText(/❌/)).toBeInTheDocument();
  expect(screen.queryByText('Chargement…')).not.toBeInTheDocument();
});

test('une erreur après un chargement réussi efface le tableau périmé au lieu de le laisser affiché', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.reconciliation
    .mockResolvedValueOnce({ year: 2025, coverage: '4/12', months: [] })
    .mockRejectedValueOnce(new Error('Erreur réseau'));

  const { rerender } = render(<MonthlyReconcileView year={2025} />);
  await screen.findByText('4/12');

  rerender(<MonthlyReconcileView year={2024} />);
  expect(await screen.findByText(/❌/)).toBeInTheDocument();
  expect(screen.queryByText('4/12')).not.toBeInTheDocument();
});

test('une erreur périmée est effacée dès le démarrage d’un nouveau fetch (changement d’année)', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  let resolve2024: (v: unknown) => void = () => {};
  monthlyBalancesAPI.reconciliation
    .mockRejectedValueOnce(new Error('Erreur réseau'))
    .mockImplementationOnce(() => new Promise((r) => { resolve2024 = r; }));

  const { rerender } = render(<MonthlyReconcileView year={2025} />);
  expect(await screen.findByText(/❌/)).toBeInTheDocument();

  rerender(<MonthlyReconcileView year={2024} />);
  // L'erreur périmée doit disparaître dès le lancement du nouveau fetch,
  // sans attendre sa résolution — sinon l'utilisateur croit que le clic
  // (le changement d'année) n'a rien fait.
  await waitFor(() => expect(screen.queryByText(/❌/)).not.toBeInTheDocument());
  expect(screen.getByText('Chargement…')).toBeInTheDocument();

  await act(async () => {
    resolve2024({ year: 2024, coverage: '2/12', months: [] });
    await Promise.resolve();
  });
  expect(screen.getByText('2/12')).toBeInTheDocument();
});
