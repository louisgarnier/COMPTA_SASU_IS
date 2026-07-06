import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TransactionsPage from '../app/transactions/page';
import { transactionsAPI } from '@/api/client';

jest.mock('@/api/client', () => ({
  transactionsAPI: {
    bulkCategorize: jest.fn((ids: number[], category_id: number | null) =>
      Promise.resolve(
        ids.map((id) => ({
          id,
          account_uid: 'acc-1',
          external_id: `ext-${id}`,
          booked_date: '2026-06-15',
          value_date: '2026-06-15',
          amount: '-10.00',
          currency: 'EUR',
          description: `tx-${id}`,
          counterparty: '',
          category_id,
          category_name: category_id ? 'Outils/SaaS' : null,
          kind: category_id ? 'charge' : 'other',
          fx_rate: null,
          amount_eur: '-10.00',
          linked_conversion_id: null,
          invoice_id: null,
          created_at: '2026-06-15T10:00:00Z',
        })),
      ),
    ),
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
    list: jest.fn().mockResolvedValue([
      { id: 5, name: 'Outils/SaaS', type: 'charge', parent_id: null, is_system: false },
    ]),
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

  it('applique la catégorie à toutes les lignes cochées (option B)', async () => {
    render(<TransactionsPage />);
    await screen.findByText('Abonnement logiciel');

    // Coche tout via l'en-tête.
    fireEvent.click(screen.getByLabelText('Tout sélectionner'));

    // Change la catégorie d'UNE ligne cochée → doit s'appliquer aux deux.
    const rowSelect = screen.getByLabelText('Catégorie de Abonnement logiciel');
    fireEvent.change(rowSelect, { target: { value: '5' } });

    await waitFor(() => expect(transactionsAPI.bulkCategorize).toHaveBeenCalled());
    const [ids, catId] = (transactionsAPI.bulkCategorize as jest.Mock).mock.calls[0];
    expect([...ids].sort()).toEqual([1, 2]);
    expect(catId).toBe(5);
  });
});
