import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { invoicesAPI } from '@/api/client';
import InvoicesPage from '../app/invoices/page';

jest.mock('next/navigation', () => ({ usePathname: () => '/invoices' }));

// Mock du client API (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  settingsAPI: {
    get: jest.fn().mockResolvedValue({ next_invoice_number: 68 }),
    update: jest.fn().mockResolvedValue({ next_invoice_number: 68 }),
  },
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
      {
        id: 3, number: '45', client_name: 'JPSB', month: '2025-03',
        period_label: 'Mars 2025', days: 0, hours: 168, rate: 120, rate_unit: 'hour',
        currency: 'USD', amount: 20160, amount_eur_forecast: 17740.8,
        issue_date: '2025-03-31', due_date: '2025-05-15', status: 'paid',
        paid_date: '2025-05-14', amount_eur_received: 17548.98, variance_eur: -191.82,
      },
    ]),
    update: jest.fn(),
    generate: jest.fn(),
    remove: jest.fn().mockResolvedValue({}),
    printUrl: (id: number) => `http://localhost:8000/api/invoices/${id}/print`,
  },
}));

describe('InvoicesPage', () => {
  it('affiche le titre, le numéro généré et les actions du cycle de vie', async () => {
    render(<InvoicesPage />);
    expect(screen.getByRole('heading', { name: /Factures/ })).toBeInTheDocument();
    // Facture 'due' → numéro éditable (input) + bouton "Ouvrir la facture"
    const numInput = (await screen.findByLabelText('N° facture 68')) as HTMLInputElement;
    expect(numInput.value).toBe('68');
    expect(await screen.findByText('Ouvrir la facture')).toBeInTheDocument();
    // Facture 'forecast' → bouton "Générer"
    expect(await screen.findByText('Générer')).toBeInTheDocument();
  });

  it('le filtre par année met à jour la LISTE, pas seulement les cartes (régression)', async () => {
    render(<InvoicesPage />);
    // Défaut = année courante (2026) : la facture 2026 est visible, la 2025 non.
    expect(await screen.findByLabelText('N° facture 68')).toBeInTheDocument();
    expect(screen.queryByLabelText('N° facture 45')).not.toBeInTheDocument();

    // Clic sur 2025 → la LISTE doit basculer (bug : seule les cartes changeaient).
    fireEvent.click(screen.getByRole('button', { name: '2025' }));
    expect(await screen.findByLabelText('N° facture 45')).toBeInTheDocument();
    expect(screen.queryByLabelText('N° facture 68')).not.toBeInTheDocument();
  });

  it('supprime une facture après confirmation', async () => {
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true);
    render(<InvoicesPage />);
    const btns = await screen.findAllByRole('button', { name: 'Supprimer' });
    fireEvent.click(btns[0]);
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => expect(invoicesAPI.remove).toHaveBeenCalledWith(1));
    confirmSpy.mockRestore();
  });

  it('ne supprime pas si la confirmation est annulée', async () => {
    (invoicesAPI.remove as jest.Mock).mockClear();
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(false);
    render(<InvoicesPage />);
    const btns = await screen.findAllByRole('button', { name: 'Supprimer' });
    fireEvent.click(btns[0]);
    expect(confirmSpy).toHaveBeenCalled();
    expect(invoicesAPI.remove).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
