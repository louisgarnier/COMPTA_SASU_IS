import { render, screen } from '@testing-library/react';
import InvoicesPage from '../app/invoices/page';

// Mock du client API (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  invoicesAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1, number: '68', client_name: 'Acme Corp', month: '2026-05',
        period_label: 'May 2026', days: 0, hours: 152, rate: 120, rate_unit: 'hour',
        currency: 'USD', amount: 18240, amount_eur_forecast: 16780.8,
        issue_date: '2026-06-01', due_date: '2026-07-31', status: 'due',
        paid_date: null, variance_eur: null,
      },
      {
        id: 2, number: 'F-2-2026-08', client_name: 'Acme Corp', month: '2026-08',
        period_label: '', days: 0, hours: 120, rate: 120, rate_unit: 'hour',
        currency: 'USD', amount: 14400, amount_eur_forecast: 13248,
        issue_date: null, due_date: null, status: 'forecast',
        paid_date: null, variance_eur: null,
      },
    ]),
    update: jest.fn(),
    generate: jest.fn(),
    printUrl: (id: number) => `http://localhost:8000/api/invoices/${id}/print`,
  },
}));

describe('InvoicesPage', () => {
  it('affiche le titre, le numéro généré et les actions du cycle de vie', async () => {
    render(<InvoicesPage />);
    expect(screen.getByRole('heading', { name: 'Factures' })).toBeInTheDocument();
    // Facture 'due' → numéro + bouton "Ouvrir la facture"
    expect(await screen.findByText('68')).toBeInTheDocument();
    expect(await screen.findByText('Ouvrir la facture')).toBeInTheDocument();
    // Facture 'forecast' → bouton "Générer"
    expect(await screen.findByText('Générer')).toBeInTheDocument();
  });
});
