import { render, screen, fireEvent } from '@testing-library/react';
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
      {
        id: 2,
        account_uid: 'acc-1',
        external_id: 'ext-2',
        booked_date: '2026-06-20',
        value_date: '2026-06-20',
        amount: '5000.00',
        currency: 'EUR',
        description: 'Virement client Acme',
        counterparty: 'Acme Corp',
        category_id: null,
        category_name: null,
        kind: 'revenue',
        fx_rate: null,
        amount_eur: '5000.00',
        linked_conversion_id: null,
        invoice_id: null,
        created_at: '2026-06-20T10:00:00Z',
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

  it('filtre les transactions par recherche texte', async () => {
    render(<TransactionsPage />);
    // Les deux transactions sont visibles au départ.
    expect(await screen.findByText('Abonnement logiciel')).toBeInTheDocument();
    expect(screen.getByText('Virement client Acme')).toBeInTheDocument();

    const box = screen.getByRole('searchbox', { name: /rechercher une transaction/i });
    fireEvent.change(box, { target: { value: 'acme' } });

    // Seule la transaction Acme reste (match sur contrepartie).
    expect(screen.getByText('Virement client Acme')).toBeInTheDocument();
    expect(screen.queryByText('Abonnement logiciel')).not.toBeInTheDocument();
  });
});
