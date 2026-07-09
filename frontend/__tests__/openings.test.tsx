import { render, screen } from '@testing-library/react';
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
});
