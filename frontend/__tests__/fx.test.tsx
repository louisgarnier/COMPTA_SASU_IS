import { render, screen } from '@testing-library/react';
import FxPage from '../app/fx/page';

jest.mock('@/api/client', () => ({
  dashboardAPI: {
    fxConversions: jest.fn().mockResolvedValue({
      conversions: [
        { date: '2026-06-25', currency: 'USD', foreign: '34505.91', eur: '30255.97', rate: '0.876834' },
        { date: '2026-06-03', currency: 'USD', foreign: '79993.92', eur: '68448.65', rate: '0.855673' },
      ],
      invoices: [
        {
          invoice_number: '60', month: '2026-01', client_code: 'SWIB', currency: 'USD',
          native: '18240.00', date_received: '2026-03-19', rate: '0.855700', eur_received: '15607.48',
          composite: false, parts: [{ date: '2026-06-03', foreign: '18240.00', rate: '0.855700' }],
        },
        {
          invoice_number: '63', month: '2026-03', client_code: 'SWIB', currency: 'USD',
          native: '16320.00', date_received: '2026-05-19', rate: '0.874275', eur_received: '14268.16',
          composite: true, parts: [
            { date: '2026-06-25', foreign: '14345.91', rate: '0.876834' },
            { date: '2026-06-03', foreign: '1974.09', rate: '0.855673' },
          ],
        },
      ],
      leftover: { USD: '116819.83', CAD: '5580.00' },
      uncovered: { USD: '0.00', CAD: '0.00' },
      totals: {
        USD: { converted_foreign: '239699.83', income_foreign: '122880.00', realized_eur: '106176.10' },
        CAD: { converted_foreign: '114646.68', income_foreign: '109066.68', realized_eur: '67612.37' },
      },
    }),
  },
}));

describe('FxPage', () => {
  it('affiche le titre, les factures et distingue réel vs composé', async () => {
    render(<FxPage />);
    expect(screen.getByRole('heading', { name: /FX \/ Conversions/ })).toBeInTheDocument();
    // Facture réelle et facture composée présentes
    expect(await screen.findByText('n°60')).toBeInTheDocument();
    expect(await screen.findByText('n°63')).toBeInTheDocument();
    // Le badge « composé · 2 » apparaît pour la facture à cheval sur 2 conversions
    expect(await screen.findByText(/composé · 2/)).toBeInTheDocument();
    // Au moins un badge « réel »
    expect((await screen.findAllByText('réel')).length).toBeGreaterThan(0);
  });
});
