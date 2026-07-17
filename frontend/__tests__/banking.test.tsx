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
  // BankingPage rend aussi MonthlyReconcileCard (EPIC-8) — mock requis sinon
  // l'effet de ce composant échoue (monthlyBalancesAPI undefined).
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: new Date().getFullYear(),
      coverage: '0/12',
      months: [],
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

  test("la carte rappro porte l'ancre visée par le lien du dashboard", async () => {
    const { container } = render(<BankingPage />);
    await waitFor(() => expect(container.querySelector('#rappro-mensuel')).not.toBeNull());
    // scroll-margin : la barre de nav mobile fixe (Nav.tsx) ne doit pas recouvrir
    // la carte à l'arrivée sur l'ancre.
    expect(container.querySelector('#rappro-mensuel')).toHaveClass('scroll-mt-20');
  });

  describe('scroll vers l’ancre après chargement', () => {
    const setHash = (hash: string) => {
      window.history.replaceState(null, '', hash ? `/banking${hash}` : '/banking');
    };

    let scrollIntoViewMock: jest.Mock;

    beforeEach(() => {
      scrollIntoViewMock = jest.fn();
      Element.prototype.scrollIntoView = scrollIntoViewMock;
    });

    afterEach(() => {
      setHash('');
    });

    it('scrolle vers l’élément désigné par le hash une fois le chargement terminé', async () => {
      setHash('#rappro-mensuel');
      const { container } = render(<BankingPage />);

      await waitFor(() => expect(container.querySelector('#rappro-mensuel')).not.toBeNull());
      await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledTimes(1));

      const target = container.querySelector('#rappro-mensuel');
      expect(scrollIntoViewMock.mock.instances[0]).toBe(target);
    });

    it("n'appelle pas scrollIntoView quand il n'y a pas de hash", async () => {
      setHash('');
      render(<BankingPage />);

      await screen.findByRole('heading', { name: 'Banques' });
      // Laisse le temps à un éventuel effet de se déclencher avant d'affirmer l'absence d'appel.
      await waitFor(() => expect(bankingAPI.connections).toHaveBeenCalled());
      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });
  });

  describe('carte « Connecter une banque » repliable', () => {
    beforeEach(() => localStorage.clear());

    // NB : viser le BOUTON « Qonto », pas le texte — « Qonto » apparaît aussi
    // comme <option> du sélecteur de banque de la carte rappro, qui elle ne se
    // replie pas. `queryByText` attraperait cette option et ne prouverait rien.
    const bankButton = () => screen.queryByRole('button', { name: 'Qonto' });

    it('est dépliée par défaut et se replie au clic', async () => {
      render(<BankingPage />);
      const toggle = await screen.findByRole('button', { name: /Connecter une banque/i });
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await waitFor(() => expect(bankButton()).toBeInTheDocument());

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      // Le corps disparaît : plus de bouton de banque ni de champ de code.
      expect(bankButton()).not.toBeInTheDocument();
      expect(screen.queryByPlaceholderText('code…')).not.toBeInTheDocument();
    });

    it('mémorise le repli — la carte reste fermée au retour sur la page', async () => {
      const first = render(<BankingPage />);
      fireEvent.click(await screen.findByRole('button', { name: /Connecter une banque/i }));
      expect(bankButton()).not.toBeInTheDocument();
      first.unmount();

      render(<BankingPage />);
      const toggle = await screen.findByRole('button', { name: /Connecter une banque/i });
      await waitFor(() => expect(toggle).toHaveAttribute('aria-expanded', 'false'));
      expect(bankButton()).not.toBeInTheDocument();
    });

    it('le reste de la page survit au repli', async () => {
      render(<BankingPage />);
      fireEvent.click(await screen.findByRole('button', { name: /Connecter une banque/i }));
      // La carte rappro (et son ancre) restent montées.
      expect(document.querySelector('#rappro-mensuel')).not.toBeNull();
      expect(screen.getByRole('heading', { name: 'Banques' })).toBeInTheDocument();
    });
  });
});
