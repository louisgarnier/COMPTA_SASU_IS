import { render, screen } from '@testing-library/react';
import TransactionsPage from '../app/transactions/page';

jest.mock('@/api/client', () => ({
  transactionsAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1,
        account_uid: 'acc-1',
        external_id: 'ext-1',
        booked_date: '2026-06-15',
        value_date: '2026-06-15',
        amount: '-34.50',
        currency: 'EUR',
        description: 'Abonnement logiciel',
        counterparty: 'Vercel',
        category_id: null,
        category_name: null,
        kind: 'charge',
        fx_rate: null,
        amount_eur: '-34.50',
        linked_conversion_id: null,
        invoice_id: null,
        created_at: '2026-06-15T10:00:00Z',
      },
    ]),
    update: jest.fn(),
  },
  categoriesAPI: {
    list: jest.fn().mockResolvedValue([]),
  },
  bankingAPI: {
    sync: jest.fn().mockResolvedValue({
      accounts_synced: 1,
      transactions_added: 0,
      transactions_skipped: 0,
    }),
  },
}));

describe('TransactionsPage', () => {
  it('affiche le titre et une transaction', async () => {
    render(<TransactionsPage />);
    expect(
      await screen.findByRole('heading', { name: 'Transactions' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Abonnement logiciel')).toBeInTheDocument();
  });
});
