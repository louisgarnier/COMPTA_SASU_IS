import { render, screen } from '@testing-library/react';
import DashboardPage from '../app/page';

// Mock du client API (nouvelle structure dashboard FreeAgent × multi-devise)
jest.mock('@/api/client', () => ({
  treasuryAPI: {
    get: jest.fn().mockResolvedValue({
      bank_total_eur: '49660.77',
      total_eur: '49660.77',
      accounts: [
        { account_uid: 'cd56227f', name: 'Revolut Main', provider: 'revolut',
          currency: 'EUR', balance: '49660.77', balance_eur: '49660.77' },
      ],
    }),
  },
  transactionsAPI: {
    // 2 transactions non catégorisées → la bannière « à catégoriser » s'affiche.
    list: jest.fn().mockResolvedValue([{ id: 1 }, { id: 2 }]),
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
    treasuryBridge: jest.fn().mockResolvedValue({
      year: 2026,
      opening_eur: '121331.03',
      lines: [
        { key: 'received_prior', label: 'Encaissé — factures < 2026', amount_eur: '43969.65' },
        { key: 'received_current', label: 'Encaissé — factures 2026', amount_eur: '144613.40' },
        { key: 'other_revenue', label: 'Autres revenus (non facturés)', amount_eur: '296.65' },
        { key: 'charges', label: 'Charges (nettes)', amount_eur: '-22050.10' },
        { key: 'cat:Dividendes / distribution dirigeant', label: 'Dividendes / distribution dirigeant', amount_eur: '-166200.00' },
        { key: 'cat:Investissement', label: 'Investissement', amount_eur: '-70000.00' },
      ],
      residual_eur: '-2299.85',
      residual_warning: false,
      bank_today_eur: '49660.78',
      due_pending_eur: '53452.80',
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
    // Libellés décision produit 2026-07 : pilotage cash hors placements.
    expect((await screen.findAllByText('Trésorerie (hors placements)')).length).toBeGreaterThan(0);
    expect(await screen.findByText('P&L (engagé)')).toBeInTheDocument();
    // Sélecteur de certitude présent (Réalisé / Engagé / Prévisionnel).
    expect(screen.getByText('Réalisé')).toBeInTheDocument();
    expect(screen.getByText('Prévisionnel')).toBeInTheDocument();
    // Bannière « à catégoriser » (2 transactions mockées) avec lien vers /transactions.
    expect(await screen.findByText(/2 transactions à catégoriser/)).toBeInTheDocument();
    // Toggle vue caisse / vue fiscale du cashflow.
    expect(screen.getByText('Année en cours')).toBeInTheDocument();
    expect(screen.getByText('Année fiscale')).toBeInTheDocument();
    // Widget pont de trésorerie : titre + lignes dynamiques + résiduel.
    expect(await screen.findByText(/D'où vient ma trésorerie/)).toBeInTheDocument();
    expect(screen.getByText(/Dividendes \/ distribution dirigeant/)).toBeInTheDocument();
    expect(screen.getByText(/Frais & écarts FX \(résiduel\)/)).toBeInTheDocument();
    // Widget soldes à une date : titre + total.
    expect(screen.getByText('Soldes bancaires à une date')).toBeInTheDocument();
    expect(screen.getByLabelText('Date des soldes')).toBeInTheDocument();
    expect(await screen.findByText('Invoice Timeline')).toBeInTheDocument();
    // Factures ouvertes : équivalent EUR approx. affiché à côté du natif.
    expect(await screen.findByText(/≈\s*3\s*864,00\s*€/)).toBeInTheDocument();
    // Le distribuable P&L est rendu (net + distribuable → au moins 1)
    expect((await screen.findAllByText(/142\s*257,66\s*€/)).length).toBeGreaterThan(0);
  });
});
