import { render, screen } from '@testing-library/react';
import HomePage from '../app/page';

// Mock the API client (même specifier que la page : @/api/client)
jest.mock('@/api/client', () => ({
  healthAPI: {
    check: jest.fn().mockResolvedValue({ status: 'healthy' }),
  },
}));

describe('HomePage', () => {
  it('affiche le titre LGC', async () => {
    render(<HomePage />);
    expect(screen.getByRole('heading', { name: 'LGC' })).toBeInTheDocument();
    // flush l'effet async (health check) pour éviter le warning act()
    await screen.findByText(/back OK/);
  });

  it('affiche l\'état du backend une fois le health check résolu', async () => {
    render(<HomePage />);
    expect(await screen.findByText(/back OK/)).toBeInTheDocument();
  });
});
