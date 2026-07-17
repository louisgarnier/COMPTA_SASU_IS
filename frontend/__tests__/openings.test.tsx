import { render, screen, fireEvent } from '@testing-library/react';
import { OpeningBalancesCard } from '../src/components/OpeningBalancesCard';

jest.mock('@/api/client', () => ({
  openingsAPI: {
    years: jest.fn().mockResolvedValue({ years: [2025, 2026] }),
    get: jest.fn().mockResolvedValue({
      year: 2026,
      accounts: [
        {
          account_uid: 'cd56227f', name: 'Revolut Main', provider: 'revolut',
          currency: 'EUR', balance: '11626.90', current_balance: '11604.73',
          rate: '1', control: { implied: '11649.07', movements: '-44.34', diff: '-22.17', status: 'warn' },
        },
        {
          account_uid: 'd48f510a', name: 'Qonto', provider: 'qonto',
          currency: 'EUR', balance: '26.78', current_balance: '26.78',
          rate: '1', control: { implied: '26.78', movements: '0', diff: '0.00', status: 'ok' },
        },
      ],
      tie_out: { opening_eur: '11653.68', current_eur: '11631.51', reconciles: true },
    }),
    save: jest.fn(),
  },
}));

describe('OpeningBalancesCard', () => {
  it('affiche la section, le contrôle concorde et l’écart signalé', async () => {
    render(<OpeningBalancesCard />);
    expect(screen.getByText("Soldes d'ouverture d'exercice")).toBeInTheDocument();
    // Écart −22,17 signalé sur Revolut Main (montant formaté par money())
    expect(await screen.findByText(/-22,17/)).toBeInTheDocument();
    // Un compte concorde
    expect(await screen.findByText(/concorde/)).toBeInTheDocument();
    // La saisie est pré-remplie dans l'input dédié
    const input = (await screen.findByLabelText('Solde Revolut Main')) as HTMLInputElement;
    expect(input.value).toBe('11626.90');
  });

  it('permet d’ajouter un exercice PASSÉ (pré-rempli à min − 1, éditable)', async () => {
    render(<OpeningBalancesCard />);
    await screen.findByText("Soldes d'ouverture d'exercice");

    // Attend que les exercices existants soient chargés (2025, 2026) avant
    // de vérifier le pré-remplissage du champ « nouvel exercice ».
    await screen.findByRole('button', { name: '2026' });
    const newYearInput = (await screen.findByLabelText(
      'Nouvel exercice à ajouter',
    )) as HTMLInputElement;
    // Pré-rempli avec l'année passée manquante (min(2025, 2026) − 1 = 2024).
    expect(newYearInput.value).toBe('2024');

    fireEvent.click(screen.getByText('+ ajouter'));

    // Le nouvel exercice 2024 apparaît comme onglet sélectionnable.
    expect(await screen.findByRole('button', { name: '2024' })).toBeInTheDocument();
  });

  it('affiche un badge d’origine quand la ligne porte une note', async () => {
    const { openingsAPI } = require('@/api/client');
    openingsAPI.get = jest.fn().mockResolvedValue({
      year: 2026,
      accounts: [{
        account_uid: 'acc', name: 'Revolut Main', provider: 'revolut', currency: 'EUR',
        balance: '11626.90', current_balance: '11626.90', rate: '1', control: null,
        note: 'relevé déc. 2025',
      }],
      tie_out: { opening_eur: '11626.90', current_eur: '11626.90', reconciles: true },
    });
    openingsAPI.years = jest.fn().mockResolvedValue({ years: [2026] });

    render(<OpeningBalancesCard />);
    expect(await screen.findByText(/relevé déc\. 2025/i)).toBeInTheDocument();
  });
});
