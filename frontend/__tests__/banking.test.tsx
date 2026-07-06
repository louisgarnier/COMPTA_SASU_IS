import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BankingPage from '../app/banking/page';
import { bankingAPI } from '@/api/client';

jest.mock('@/api/client', () => ({
  bankingAPI: {
    status: jest.fn().mockResolvedValue({ live: false, message: 'démo' }),
    aspsps: jest.fn().mockResolvedValue([{ name: 'Qonto' }]),
    connect: jest.fn().mockResolvedValue({ authorization_url: 'http://x', state: 'st-1' }),
    createSession: jest.fn().mockResolvedValue({
      session_id: 'mock',
      accounts: [
        { account_uid: 'u-rev', provider: 'revolut', currency: 'EUR', iban_masked: 'FR76****01', name: 'Revolut EUR' },
        { account_uid: 'u-qonto', provider: 'qonto', currency: 'EUR', iban_masked: 'FR76****42', name: 'Qonto Courant' },
      ],
    }),
    selectAccounts: jest.fn().mockResolvedValue([{ id: 1 }]),
    connections: jest.fn().mockResolvedValue([]),
    disconnect: jest.fn(),
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

  it('flux connexion → sélection : ne rattache que les comptes cochés + envoie le state', async () => {
    render(<BankingPage />);
    await screen.findByRole('heading', { name: 'Banques' });

    // Connexion → récupère le state OAuth.
    fireEvent.click(await screen.findByText('Qonto'));
    await waitFor(() => expect(bankingAPI.connect).toHaveBeenCalled());

    // Saisie du code + validation → aperçu des comptes.
    fireEvent.change(screen.getByPlaceholderText('code…'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider le code' }));

    // Le code est échangé AVEC le state émis (anti-CSRF).
    await waitFor(() =>
      expect(bankingAPI.createSession).toHaveBeenCalledWith('abc', 'st-1'),
    );

    // Les deux comptes apparaissent ; on décoche Revolut.
    expect(await screen.findByText('Revolut EUR')).toBeInTheDocument();
    const revBox = screen.getByLabelText(/Revolut EUR/i, { selector: 'input' });
    fireEvent.click(revBox); // décoche

    fireEvent.click(screen.getByRole('button', { name: /Rattacher les comptes/ }));

    // Seul Qonto (coché) est envoyé à selectAccounts.
    await waitFor(() => expect(bankingAPI.selectAccounts).toHaveBeenCalled());
    const sent = (bankingAPI.selectAccounts as jest.Mock).mock.calls[0][0];
    expect(sent).toHaveLength(1);
    expect(sent[0].provider).toBe('qonto');
  });
});
