/** Helpers dates partagés (widgets tréso). */

import { dateFR } from '@/lib/format';

export const isoDate = (d: Date) => d.toISOString().slice(0, 10);

/**
 * Raccourcis de dates pour un exercice donné (défaut : celui d'aujourd'hui).
 * - Exercice courant : 31/12 N-1 + fins de trimestre écoulées + aujourd'hui.
 * - Exercice passé : 31/12 N-1 + fins de trimestre + 31/12 N (exercice complet).
 */
export function dateShortcuts(today: Date, year?: number): { label: string; date: string }[] {
  const cur = today.getFullYear();
  const y = year ?? cur;
  const out = [{ label: `31/12/${String(y - 1).slice(2)}`, date: `${y - 1}-12-31` }];
  const quarters = [`${y}-03-31`, `${y}-06-30`, `${y}-09-30`];
  if (y < cur) {
    for (const q of quarters) out.push({ label: dateFR(q), date: q });
    out.push({ label: `31/12/${String(y).slice(2)}`, date: `${y}-12-31` });
  } else {
    for (const q of quarters) if (q <= isoDate(today)) out.push({ label: dateFR(q), date: q });
    out.push({ label: "Aujourd'hui", date: isoDate(today) });
  }
  return out;
}
