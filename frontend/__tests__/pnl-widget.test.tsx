import { render, screen } from '@testing-library/react';
import { PnlWidget, PnlSummary } from '../src/components/dashboard/PnlWidget';

const base: PnlSummary = {
  year: 2026,
  is_regime: 'IS',
  revenue_eur: '198279.60',
  charges_eur: '22081.66',
  result_eur: '176197.94',
  is_estimate_eur: '39799.48',
  net_result_eur: '136398.46',
  retained_earnings_eur: '166200.00',
  distributable_eur: '302598.46',
  by_currency: [],
};

describe('PnlWidget — distribuable (maquette 2026-07-09)', () => {
  it('scénario 1 : versements = RAN → RAN net 0, restant = net, mention « soldé »', () => {
    render(<PnlWidget data={{ ...base, distributed_this_year_eur: '166200.00', remaining_distributable_eur: '136398.46' }} />);
    expect(screen.getByText('Report à nouveau (net des versements)')).toBeInTheDocument();
    expect(screen.getByText('Distribuable (restant)')).toBeInTheDocument();
    expect(screen.getByText(/→ soldé/)).toBeInTheDocument();
    // Pas d'acomptes ni d'alerte.
    expect(screen.queryByText(/Acomptes sur l'exercice/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sur-distribution/)).not.toBeInTheDocument();
  });

  it('scénario 2 : versements > RAN → terme « Acomptes », restant réduit', () => {
    render(<PnlWidget data={{ ...base, distributed_this_year_eur: '216200.00', remaining_distributable_eur: '86398.46' }} />);
    expect(screen.getByText("Acomptes sur l'exercice")).toBeInTheDocument();
    // L'excédent apparaît 2× : la cellule Acomptes + la mention du bas.
    expect(screen.getAllByText(/50\s*000,00\s*€/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/86\s*398,46\s*€/)).toBeInTheDocument();     // le restant
    expect(screen.getByText(/dont .*en acompte sur le résultat 2026/)).toBeInTheDocument();
  });

  it('garde-fou : sur-distribution → restant négatif + alerte, RAN jamais négatif', () => {
    render(<PnlWidget data={{ ...base, distributed_this_year_eur: '320000.00', remaining_distributable_eur: '-17401.54' }} />);
    expect(screen.getByText(/sur-distribution à régulariser/)).toBeInTheDocument();
    expect(screen.getByText(/-17\s*401,54\s*€/)).toBeInTheDocument();
    // Le RAN affiché reste 0, pas négatif.
    expect(screen.getByText('Report à nouveau (net des versements)')).toBeInTheDocument();
  });

  it('exercice sans versement : équation classique « cumul auto »', () => {
    render(<PnlWidget data={{ ...base, retained_earnings_eur: '136398.46', distributable_eur: '228898.46', distributed_this_year_eur: '0.00', remaining_distributable_eur: '228898.46' }} />);
    expect(screen.getByText('Report à nouveau (cumul auto)')).toBeInTheDocument();
    expect(screen.queryByText(/Report à nouveau initial/)).not.toBeInTheDocument();
  });
});
