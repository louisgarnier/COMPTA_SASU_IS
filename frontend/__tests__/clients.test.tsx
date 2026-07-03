import { render, screen } from '@testing-library/react';
import ClientsPage from '../app/clients/page';

jest.mock('@/api/client', () => ({
  clientsAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1, code: 'SWIB', legal_name: 'Alpha Financial Markets Consulting Inc.',
        address: '437 Madison Ave', country: 'USA', contact_name: '', email: '',
        currency: 'USD', tjh: '120', billing_mode: 'thm', default_hours_per_day: '8', payment_terms_days: 60,
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
    expect(screen.getByText('Taux (jour/heure)')).toBeInTheDocument();
    expect(screen.getByText('Échéance (jours)')).toBeInTheDocument();
    // Mode de facturation (TJM/THM) présent comme select
    expect(screen.getByText('Mode')).toBeInTheDocument();
    // La devise est un menu déroulant (pas un texte libre) avec les devises supportées
    const selects = screen.getAllByRole('combobox') as HTMLSelectElement[];
    const devise = selects.find((s) =>
      Array.from(s.options).some((o) => o.value === 'USD'),
    )!;
    const options = Array.from(devise.options).map((o) => o.value);
    expect(options).toEqual(expect.arrayContaining(['EUR', 'USD', 'CAD', 'GBP']));
  });
});
