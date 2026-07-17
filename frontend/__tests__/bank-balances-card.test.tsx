import type { ReactNode } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BankBalancesCard } from '@/components/dashboard/BankBalancesCard';

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock('@/api/client', () => ({
  balanceDocsAPI: { downloadUrl: (id: number) => `/api/balance-docs/${id}/download` },
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({
      as_of: '2025-12-31',
      bank_total_eur: '126493.91',
      accounts: [{
        account_uid: 'cd56227f-c427', name: 'Revolut Main', provider: 'revolut',
        currency: 'EUR', balance: '11626.90', balance_eur: '11626.90',
      }],
    }),
  },
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025, coverage: '4/12',
      months: [{
        month: 12, status: 'ok', total_eur_official: '126493.91',
        total_eur_diff: '0.00', per_account: [], docs: [],
      }],
    }),
  },
}));

// Note : le compte mocké est nativement en EUR, donc « solde natif » et
// « équiv. EUR » affichent la même chaîne dans la même ligne (2 nœuds) —
// on utilise findAllByText comme dans dashboard.test.tsx plutôt que
// findByText (singulier), qui échouerait avec « Found multiple elements ».

test('ouvre sur l’onglet Soldes à une date', async () => {
  render(<BankBalancesCard year={2025} />);
  expect((await screen.findAllByText('11 626,90 €')).length).toBeGreaterThan(0);
  // L'onglet rappro n'est pas monté tant qu'on ne clique pas.
  expect(screen.queryByText(/Couverture/)).not.toBeInTheDocument();
});

test('la pilule bascule sur le rapprochement mensuel', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  render(<BankBalancesCard year={2025} />);
  await screen.findAllByText('11 626,90 €');

  fireEvent.click(screen.getByRole('button', { name: /Rapprochement mensuel/i }));
  expect(await screen.findByText('4/12')).toBeInTheDocument();
  expect(await screen.findByText(/Déc 2025/)).toBeInTheDocument();
  expect(monthlyBalancesAPI.reconciliation).toHaveBeenCalled();
});

test('la pilule revient sur les soldes', async () => {
  render(<BankBalancesCard year={2025} />);
  await screen.findAllByText('11 626,90 €');
  fireEvent.click(screen.getByRole('button', { name: /Rapprochement mensuel/i }));
  await screen.findByText('4/12');

  fireEvent.click(screen.getByRole('button', { name: /Soldes à une date/i }));
  expect((await screen.findAllByText('11 626,90 €')).length).toBeGreaterThan(0);
  expect(screen.queryByText('4/12')).not.toBeInTheDocument();
});
