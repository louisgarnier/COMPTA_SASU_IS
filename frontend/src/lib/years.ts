/**
 * Exercices proposés par le sélecteur de la Facturation.
 *
 * Borne basse DÉRIVÉE DES DONNÉES (aucune année en dur) : un exercice sous la
 * plus ancienne facture connue (on peut toujours saisir l'exercice précédent —
 * ex. factures 2024 payées début 2025), au minimum un sous l'année précédente.
 * Borne haute : année courante + 2 (horizon forecast).
 */
export function facturationYears(invoiceMonths: string[], curYear: number): number[] {
  const years = invoiceMonths
    .map((m) => parseInt((m || '').slice(0, 4), 10))
    .filter((y) => Number.isFinite(y));
  const first = Math.min(years.length ? Math.min(...years) : curYear, curYear - 1) - 1;
  const out: number[] = [];
  for (let y = first; y <= curYear + 2; y += 1) out.push(y);
  return out;
}
