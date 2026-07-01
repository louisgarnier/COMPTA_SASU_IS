import { render, screen } from '@testing-library/react';
import InvoicesPage from '../app/invoices/page';

// Mock du client API (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  invoicesAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1,
        number: 'F-2026-001',
        client_id: 1,
        client_name: 'Acme Corp',
        period_label: 'Juin 2026',
        period_start: '2026-06-01',
        period_end: '2026-06-30',
        hours: 10,
        rate: 800,
        currency: 'EUR',
        amount: 8000,
        issue_date: '2026-07-01',
        due_date: '2026-07-31',
        status: 'sent',
        paid_transaction_id: null,
        pdf_path: null,
      },
    ]),
    update: jest.fn(),
    create: jest.fn(),
    generatePdf: jest.fn(),
    downloadUrl: (id: number) => `http://localhost:8000/api/invoices/${id}/download`,
  },
  clientsAPI: {
    list: jest.fn().mockResolvedValue([
      { id: 1, code: 'ACME', legal_name: 'Acme Corp', currency: 'EUR', tjh: 800 },
    ]),
  },
}));

describe('InvoicesPage', () => {
  it('affiche le titre et le numéro de facture', async () => {
    render(<InvoicesPage />);
    expect(screen.getByRole('heading', { name: 'Factures' })).toBeInTheDocument();
    expect(await screen.findByText('F-2026-001')).toBeInTheDocument();
  });
});
