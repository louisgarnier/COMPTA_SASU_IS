import { render, screen } from '@testing-library/react';
import BankingPage from '../app/banking/page';

jest.mock('@/api/client', () => ({
  bankingAPI: {
    status: jest.fn().mockResolvedValue({ live: false, message: 'démo' }),
    aspsps: jest.fn().mockResolvedValue([{ name: 'Qonto' }]),
    connect: jest.fn(),
    createSession: jest.fn().mockResolvedValue([]),
    connections: jest.fn().mockResolvedValue([]),
    sync: jest.fn().mockResolvedValue({
      accounts_synced: 0,
      transactions_added: 0,
      transactions_skipped: 0,
    }),
  },
}));

describe('BankingPage', () => {
  it('affiche le titre et une banque disponible', async () => {
    render(<BankingPage />);
    expect(
      await screen.findByRole('heading', { name: 'Banques' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Qonto')).toBeInTheDocument();
  });
});
