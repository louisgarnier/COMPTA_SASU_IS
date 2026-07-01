import { render, screen } from '@testing-library/react';
import CategoriesPage from '../app/categories/page';

// Mock the API client (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  categoriesAPI: {
    list: jest.fn().mockResolvedValue([
      { id: 1, name: 'Ventes SaaS', type: 'revenue', parent_id: null, is_system: false },
    ]),
    listRules: jest.fn().mockResolvedValue([
      {
        id: 10,
        match_field: 'counterparty',
        pattern: 'stripe',
        category_id: 1,
        priority: 100,
        enabled: true,
      },
    ]),
    create: jest.fn(),
    update: jest.fn(),
    createRule: jest.fn(),
    updateRule: jest.fn(),
    deleteRule: jest.fn(),
  },
}));

describe('CategoriesPage', () => {
  it('affiche le titre Catégories', async () => {
    render(<CategoriesPage />);
    expect(
      screen.getByRole('heading', { name: 'Catégories' }),
    ).toBeInTheDocument();
    // flush l'effet async (chargement des données)
    const matches = await screen.findAllByText('Ventes SaaS');
    expect(matches.length).toBeGreaterThan(0);
  });

  it('affiche la catégorie une fois les données chargées', async () => {
    render(<CategoriesPage />);
    const matches = await screen.findAllByText('Ventes SaaS');
    expect(matches[0]).toBeInTheDocument();
  });
});
