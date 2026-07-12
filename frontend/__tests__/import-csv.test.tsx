import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ImportCsvCard from '@/components/ImportCsvCard';

// Pas de @testing-library/user-event dans les dépendances du projet (voir
// __tests__/banking.test.tsx) : on simule l'upload via fireEvent.change,
// convention déjà utilisée pour les autres inputs de ce repo.

const previewPayload = {
  bank: 'revolut',
  rows_read: 2,
  period: { min: '2025-01-02', max: '2025-12-30' },
  importable: 2,
  out_of_period: 0,
  duplicates: 0,
  skipped_no_account: 0,
  accounts: [
    {
      csv_name: 'EUR Main', iban_masked: 'FR76****27', currency: 'EUR',
      tx_count: 2, matched: true, account_id: 2, account_name: 'Revolut EUR',
      opening_balance: '100.00', closing_balance: '80.00',
    },
  ],
  sample: [
    { date: '2025-01-02', description: 'SNCF', amount: '-127.00', currency: 'EUR', account: 'EUR Main' },
  ],
  warnings: [],
};

beforeEach(() => {
  global.fetch = jest.fn((url: string) =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve(
          String(url).includes('preview')
            ? previewPayload
            : { bank: 'revolut', inserted: 2, duplicates: 0, out_of_period: 0,
                skipped_no_account: 0, categorized: 1,
                backup_file: 'lgc_20260712_101502_import.db', accounts_touched: 1, warnings: [] }
        ),
    })
  ) as jest.Mock;
});

test('upload → prévisualisation → import → rapport', async () => {
  render(<ImportCsvCard />);

  const file = new File(['Date started (UTC),...'], 'revolut.csv', { type: 'text/csv' });
  const input = screen.getByTestId('import-file-input') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });

  await waitFor(() => expect(screen.getByText(/Prévisualisation/)).toBeInTheDocument());
  expect(screen.getByText(/Revolut/i)).toBeInTheDocument();
  expect(screen.getByText(/Existant · Revolut EUR/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Importer 2 transactions/ }));
  await waitFor(() => expect(screen.getByText(/Rapport d'import/)).toBeInTheDocument());
  expect(screen.getByText('2')).toBeInTheDocument(); // insérées
  expect(screen.getByText(/lgc_20260712_101502_import\.db/)).toBeInTheDocument();
});
