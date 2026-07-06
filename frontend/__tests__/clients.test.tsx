import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ClientsPage from '../app/clients/page';
import { clientsAPI } from '@/api/client';

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
    update: jest.fn().mockResolvedValue({}),
    remove: jest.fn(),
    repricePreview: jest.fn(),
    reprice: jest.fn().mockResolvedValue({ count: 1 }),
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

  it('propose de repropager aux prévisions quand le taux change, puis applique', async () => {
    (clientsAPI.repricePreview as jest.Mock).mockResolvedValue({
      from_month: '2026-07', count: 2, currency: 'USD', rate: '130', rate_unit: 'hour',
      rows: [
        { month: '2026-08', quantity: '96', unit: 'h', old_amount: '12000', new_amount: '12480', old_amount_eur: '11040', new_amount_eur: '11481.60' },
      ],
      total_old: '27000', total_new: '28080', total_old_eur: '24840', total_new_eur: '25833.60',
    });

    render(<ClientsPage />);
    // Sélectionne SWIB
    fireEvent.click(await screen.findByText(/Alpha Financial/));
    // Change le taux 120 → 130
    const rate = screen.getByDisplayValue('120') as HTMLInputElement;
    fireEvent.change(rate, { target: { value: '130' } });
    // Enregistre
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    // La modale de repropagation apparaît
    const applyBtn = await screen.findByRole('button', { name: /Appliquer aux 2 prévision/ });
    expect(clientsAPI.repricePreview).toHaveBeenCalledWith(1);
    expect(screen.getByText(/Appliquer le nouveau taux/)).toBeInTheDocument();

    // Applique → appelle l'API reprice
    fireEvent.click(applyBtn);
    await waitFor(() => expect(clientsAPI.reprice).toHaveBeenCalledWith(1));
  });

  it('ne propose rien si le taux et le mode sont inchangés', async () => {
    (clientsAPI.repricePreview as jest.Mock).mockClear();
    render(<ClientsPage />);
    fireEvent.click(await screen.findByText(/Alpha Financial/));
    // Enregistre sans changer le taux
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    await waitFor(() => expect(clientsAPI.update).toHaveBeenCalled());
    expect(clientsAPI.repricePreview).not.toHaveBeenCalled();
  });
});
