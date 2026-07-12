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
  // Tuile « Banque détectée » : ancrée par testid pour éviter toute ambiguïté
  // avec le badge « Existant · Revolut EUR » (le nom de compte reprend souvent
  // le nom de la banque).
  expect(screen.getByTestId('preview-bank')).toHaveTextContent(/Revolut Business/);
  expect(screen.getByText(/Existant · Revolut EUR/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Importer 2 transactions/ }));
  await waitFor(() => expect(screen.getByText(/Rapport d'import/)).toBeInTheDocument());
  expect(screen.getByText('2')).toBeInTheDocument(); // insérées
  expect(screen.getByText(/lgc_20260712_101502_import\.db/)).toBeInTheDocument();
});

test('erreur API en prévisualisation → message affiché, retour à la zone de dépôt', async () => {
  // Le helper `post` de client.ts lit le corps JSON de la réponse !ok et jette
  // une Error(extractErrorMessage) portant le `detail` — on mocke ce cas.
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Format CSV non reconnu' }),
    })
  ) as jest.Mock;

  render(<ImportCsvCard />);

  const file = new File(['n importe quoi'], 'inconnu.csv', { type: 'text/csv' });
  const input = screen.getByTestId('import-file-input') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });

  // Le detail de l'API remonte dans la carte, non avalé.
  await waitFor(() =>
    expect(screen.getByText(/Format CSV non reconnu/)).toBeInTheDocument()
  );
  // Retour à l'état idle : zone de dépôt réaffichée, pas de prévisualisation.
  expect(screen.getByText(/Glissez-déposez/)).toBeInTheDocument();
  expect(screen.queryByText(/Prévisualisation/)).not.toBeInTheDocument();
});
