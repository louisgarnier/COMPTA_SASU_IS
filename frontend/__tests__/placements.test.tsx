import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PlacementsPage from '../app/placements/page';
import { investmentsAPI, fxAPI } from '@/api/client';

jest.mock('@/api/client', () => ({
  investmentsAPI: {
    list: jest.fn().mockResolvedValue([
      {
        id: 1, label: 'Bitcoin', type: 'crypto', currency: 'EUR',
        opening_value: '10000', opening_value_eur: '10000',
        current_value: '13000', current_value_eur: '13000',
        as_of_date: '2026-07-01', note: '',
      },
    ]),
    summary: jest.fn().mockResolvedValue({
      total_opening_value_eur: '10000', total_current_value_eur: '13000', gain_eur: '3000',
    }),
    create: jest.fn().mockResolvedValue({}),
    update: jest.fn(),
    remove: jest.fn(),
  },
  fxAPI: {
    list: jest.fn().mockResolvedValue([{ currency: 'USD', rate: '0.92', missing: false }]),
    save: jest.fn(),
  },
}));

describe('PlacementsPage', () => {
  it('affiche le résumé et la liste des placements', async () => {
    render(<PlacementsPage />);
    expect(await screen.findByText('Bitcoin')).toBeInTheDocument();
    expect(screen.getByText('Plus-value latente')).toBeInTheDocument();
    // +3 000,00 apparaît dans la tuile résumé ET la ligne (+/-).
    expect(screen.getAllByText(/\+3\s?000,00/).length).toBeGreaterThanOrEqual(1);
  });

  it('crée un placement en convertissant la valeur EUR au taux FX', async () => {
    render(<PlacementsPage />);
    await screen.findByText('Bitcoin');
    fireEvent.change(screen.getByPlaceholderText('Bitcoin (Kraken)'), { target: { value: 'ETH USD' } });
    // devise USD (taux 0.92)
    const selects = screen.getAllByRole('combobox');
    const devise = selects.find((s) =>
      Array.from((s as HTMLSelectElement).options).some((o) => o.value === 'USD'),
    ) as HTMLSelectElement;
    fireEvent.change(devise, { target: { value: 'USD' } });
    fireEvent.change(screen.getByPlaceholderText('10000'), { target: { value: '1000' } });
    fireEvent.change(screen.getByPlaceholderText('13000'), { target: { value: '2000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    await waitFor(() => expect(investmentsAPI.create).toHaveBeenCalled());
    const payload = (investmentsAPI.create as jest.Mock).mock.calls[0][0];
    expect(payload.currency).toBe('USD');
    expect(payload.opening_value_eur).toBeCloseTo(920); // 1000 × 0.92
    expect(payload.current_value_eur).toBeCloseTo(1840); // 2000 × 0.92
  });
});
