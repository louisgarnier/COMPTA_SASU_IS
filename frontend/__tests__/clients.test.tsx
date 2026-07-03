import { render, screen } from '@testing-library/react';
import ClientsPage from '../app/clients/page';

jest.mock('@/api/client', () => ({
  clientsAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1, code: 'SWIB', legal_name: 'Alpha Financial Markets Consulting Inc.',
        address: '437 Madison Ave', country: 'USA', contact_name: '', email: '',
        currency: 'USD', tjh: '120', default_hours_per_day: '8', payment_terms_days: 60,
        pay_iban: '', counterparty_match: 'ALPHA FINANCIAL',
      },
    ]),
    create: jest.fn(),
    update: jest.fn(),
    remove: jest.fn(),
  },
}));

describe('ClientsPage', () => {
  it('affiche le titre et la liste des clients', async () => {
    render(<ClientsPage />);
    expect(await screen.findByRole('heading', { name: 'Clients' })).toBeInTheDocument();
    expect(await screen.findByText(/Alpha Financial/)).toBeInTheDocument();
    // Champs de facturation présents dans le formulaire
    expect(screen.getByText('Taux horaire')).toBeInTheDocument();
    expect(screen.getByText('Échéance (jours)')).toBeInTheDocument();
  });
});
