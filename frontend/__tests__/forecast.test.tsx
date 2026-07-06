import { render, screen } from '@testing-library/react';
import ForecastPage from '../app/forecast/page';

// Mock du client API (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  forecastAPI: {
    get: jest.fn().mockResolvedValue({
      inputs: [
        {
          month: '2026-07', client_id: 1, days: 10, hours: 80,
          rate: '600', rate_unit: 'day', note: '',
        },
      ],
      projection: {
        months: [
          {
            month: '2026-07', revenue_eur: '6000.00', charges_eur: '1200.00',
            net_eur: '4800.00', cumulative_cash_eur: '4800.00', is_forecast: true,
          },
          {
            month: '2026-08', revenue_eur: '0.00', charges_eur: '1200.00',
            net_eur: '-1200.00', cumulative_cash_eur: '3600.00', is_forecast: true,
          },
        ],
        totals: { revenue_eur: '6000.00', charges_eur: '2400.00' },
      },
      is: {
        base_eur: '3600.00', threshold_eur: '42500.00', low_rate: '0.15',
        high_rate: '0.25', is_low_eur: '540.00', is_high_eur: '0.00', is_total_eur: '540.00',
      },
    }),
    save: jest.fn(),
  },
  clientsAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1, code: 'ACME', legal_name: 'Acme Corp', currency: 'EUR',
        tjh: '600', billing_mode: 'tjm', default_hours_per_day: '8',
      },
    ]),
    update: jest.fn(),
  },
  fxAPI: {
    list: jest.fn().mockResolvedValue([{ currency: 'USD', rate: '0.9' }]),
  },
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({ total_eur: '0' }),
  },
}));

describe('ForecastPage', () => {
  it('affiche le titre Forecast et une valeur en euros', async () => {
    render(<ForecastPage />);
    // Titre présent immédiatement
    expect(screen.getByRole('heading', { name: 'Forecast' })).toBeInTheDocument();
    // Une valeur euro apparaît après résolution des appels async
    // (fr-FR utilise une espace insécable étroite comme séparateur → matcher souple)
    expect((await screen.findAllByText((c) => /000,00/.test(c) && /€/.test(c))).length).toBeGreaterThan(0);
    // Le client mocké est rendu dans la grille de saisie
    expect(await screen.findByText(/Acme Corp/)).toBeInTheDocument();
  });
});
