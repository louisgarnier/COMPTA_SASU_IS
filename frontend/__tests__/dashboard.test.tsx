import { render, screen } from '@testing-library/react';
import DashboardPage from '../app/page';

// Mock du client API (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({
      accounts: [
        {
          account_uid: 'acc-1',
          name: 'Compte pro',
          provider: 'Qonto',
          currency: 'EUR',
          balance: '12345.67',
        },
      ],
      bank_total_eur: '12345.67',
      investments_total_eur: '5000.00',
      total_eur: '17345.67',
    }),
    pnl: jest.fn().mockResolvedValue({
      year: 2026,
      months: Array.from({ length: 12 }, (_, i) => ({
        month: `2026-${String(i + 1).padStart(2, '0')}`,
        revenue_eur: '1000.00',
        charges_eur: '-400.00',
        result_eur: '600.00',
      })),
      totals: { revenue_eur: '12000.00', charges_eur: '-4800.00', result_eur: '7200.00' },
    }),
  },
  investmentsAPI: {
    summary: jest.fn().mockResolvedValue({
      total_opening_value_eur: '4500.00',
      total_current_value_eur: '5000.00',
      gain_eur: '500.00',
    }),
  },
  forecastAPI: {
    get: jest.fn().mockResolvedValue({
      inputs: [],
      projection: {
        months: Array.from({ length: 12 }, (_, i) => ({
          month: `2026-${String(i + 1).padStart(2, '0')}`,
          revenue_eur: '1000.00',
          charges_eur: '-400.00',
          net_eur: '600.00',
          cumulative_cash_eur: `${600 * (i + 1)}.00`,
        })),
        totals: { revenue_eur: '12000.00', charges_eur: '-4800.00' },
      },
      is: {
        base_eur: '7200.00',
        threshold_eur: '42500.00',
        low_rate: '0.15',
        high_rate: '0.25',
        is_low_eur: '1080.00',
        is_high_eur: '0.00',
        is_total_eur: '1080.00',
      },
    }),
  },
}));

describe('DashboardPage', () => {
  it('affiche le titre et la trésorerie totale formatée', async () => {
    render(<DashboardPage />);
    // Le titre est rendu immédiatement (état loading)
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    // Total tréso formaté en euros une fois les données résolues
    expect(await screen.findByText(/17\s*345,67\s*€/)).toBeInTheDocument();
  });
});
