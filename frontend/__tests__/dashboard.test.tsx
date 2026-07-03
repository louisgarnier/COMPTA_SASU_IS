import { render, screen } from '@testing-library/react';
import DashboardPage from '../app/page';

// Mock du client API (nouvelle structure dashboard FreeAgent × multi-devise)
jest.mock('@/api/client', () => ({
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({
      bank_total_eur: '49660.77',
      total_eur: '49660.77',
    }),
  },
  dashboardAPI: {
    cashflow: jest.fn().mockResolvedValue({
      year: 2026,
      months: Array.from({ length: 12 }, (_, i) => ({
        month: `2026-${String(i + 1).padStart(2, '0')}`,
        incoming_by_ccy: { EUR: '1000.00' },
        outgoing_by_ccy: { EUR: '400.00' },
        incoming_eur: '1000.00',
        outgoing_eur: '400.00',
        is_forecast: i >= 6,
      })),
      totals: { incoming_eur: '12000.00', outgoing_eur: '4800.00', net_eur: '7200.00' },
    }),
    balanceTimeline: jest.fn().mockResolvedValue({
      year: 2026,
      months: Array.from({ length: 12 }, (_, i) => ({
        month: `2026-${String(i + 1).padStart(2, '0')}`,
        balance_eur: `${1000 * (i + 1)}.00`,
        is_forecast: i >= 6,
      })),
      current_balance_eur: '49660.77',
      projected_year_end_eur: '128400.00',
    }),
    pnlSummary: jest.fn().mockResolvedValue({
      revenue_eur: '202222.92',
      charges_eur: '18212.70',
      result_eur: '184010.22',
      is_estimate_eur: '41752.56',
      net_result_eur: '142257.66',
      retained_earnings_eur: '0.00',
      distributable_eur: '142257.66',
      by_currency: [
        { currency: 'EUR', revenue_native: '15007.98', revenue_eur: '15007.98', charges_eur: '17926.19' },
      ],
    }),
    invoiceTimeline: jest.fn().mockResolvedValue({
      months: [{ month: '2026-06', paid_eur: '2000.00', due_eur: '0.00', overdue_eur: '500.00' }],
      outstanding_eur: '6175.03',
      open: [
        { number: 'F-2026-061', client_code: 'SWIB', currency: 'USD', amount: '4200.00', amount_eur: '3864.00', status: 'overdue' },
      ],
      open_count: 1,
    }),
  },
}));

describe('DashboardPage', () => {
  it('affiche le titre et la trésorerie totale formatée', async () => {
    render(<DashboardPage />);
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect((await screen.findAllByText(/49\s*660,77\s*€/)).length).toBeGreaterThan(0);
  });

  it('affiche les 4 widgets FreeAgent', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText(/Cashflow/)).toBeInTheDocument();
    expect(await screen.findByText('Solde de trésorerie')).toBeInTheDocument();
    expect(await screen.findByText('Profit & Loss (live)')).toBeInTheDocument();
    expect(await screen.findByText('Invoice Timeline')).toBeInTheDocument();
    // Le distribuable P&L est rendu (net + distribuable → au moins 1)
    expect((await screen.findAllByText(/142\s*257,66\s*€/)).length).toBeGreaterThan(0);
  });
});
