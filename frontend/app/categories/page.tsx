'use client';

import { useEffect, useState } from 'react';
import { categoriesAPI } from '@/api/client';
import { PageTitle, Card, Badge, Empty } from '@/components/ui';

type CategoryType =
  | 'revenue'
  | 'charge'
  | 'conversion'
  | 'transfer'
  | 'internal'
  | 'uncategorized';

type Category = {
  id: number;
  name: string;
  type: CategoryType;
  parent_id: number | null;
  is_system: boolean;
};

type MatchField = 'counterparty' | 'description';

type Rule = {
  id: number;
  match_field: MatchField;
  pattern: string;
  category_id: number;
  priority: number;
  enabled: boolean;
};

const TYPE_OPTIONS: { value: CategoryType; label: string }[] = [
  { value: 'revenue', label: 'Recette' },
  { value: 'charge', label: 'Charge' },
  { value: 'conversion', label: 'Conversion' },
  { value: 'transfer', label: 'Virement' },
  { value: 'internal', label: 'Interne' },
  { value: 'uncategorized', label: 'Non catégorisé' },
];

const FIELD_OPTIONS: { value: MatchField; label: string }[] = [
  { value: 'counterparty', label: 'Contrepartie' },
  { value: 'description', label: 'Libellé' },
];

function typeTone(type: CategoryType): 'pos' | 'neg' | 'warn' | 'neutral' {
  if (type === 'revenue') return 'pos';
  if (type === 'charge') return 'neg';
  if (type === 'uncategorized') return 'warn';
  return 'neutral';
}

function typeLabel(type: CategoryType): string {
  return TYPE_OPTIONS.find((o) => o.value === type)?.label ?? type;
}

const inputClass =
  'rounded-lg border border-[var(--border)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]';
const btnClass =
  'rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50';

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Formulaire nouvelle catégorie
  const [newCatName, setNewCatName] = useState('');
  const [newCatType, setNewCatType] = useState<CategoryType>('charge');

  // Formulaire nouvelle règle
  const [newRuleField, setNewRuleField] = useState<MatchField>('counterparty');
  const [newRulePattern, setNewRulePattern] = useState('');
  const [newRuleCategory, setNewRuleCategory] = useState<number | ''>('');
  const [newRulePriority, setNewRulePriority] = useState('100');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [cats, rls] = await Promise.all([
        categoriesAPI.list() as Promise<Category[]>,
        categoriesAPI.listRules() as Promise<Rule[]>,
      ]);
      setCategories(cats);
      setRules(rls);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const categoryName = (id: number): string =>
    categories.find((c) => c.id === id)?.name ?? `#${id}`;

  const addCategory = async () => {
    if (!newCatName.trim()) return;
    try {
      await categoriesAPI.create({ name: newCatName.trim(), type: newCatType });
      setNewCatName('');
      setNewCatType('charge');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const addRule = async () => {
    if (!newRulePattern.trim() || newRuleCategory === '') return;
    try {
      await categoriesAPI.createRule({
        match_field: newRuleField,
        pattern: newRulePattern.trim(),
        category_id: Number(newRuleCategory),
        priority: Number(newRulePriority) || 0,
        enabled: true,
      });
      setNewRulePattern('');
      setNewRulePriority('100');
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const toggleRule = async (rule: Rule, enabled: boolean) => {
    try {
      await categoriesAPI.updateRule(rule.id, { enabled });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const changeRuleCategory = async (rule: Rule, categoryId: number) => {
    try {
      await categoriesAPI.updateRule(rule.id, { category_id: categoryId });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const removeRule = async (id: number) => {
    try {
      await categoriesAPI.deleteRule(id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const removeCategory = async (c: Category) => {
    if (!confirm(`Supprimer la catégorie « ${c.name} » ? Les transactions dessus repassent à « À catégoriser ».`)) return;
    try {
      await categoriesAPI.remove(c.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const patchRule = async (rule: Rule, body: Record<string, unknown>) => {
    try {
      await categoriesAPI.updateRule(rule.id, body);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const [recatMsg, setRecatMsg] = useState('');
  const reapplyRules = async () => {
    setRecatMsg('Ré-application…');
    try {
      const res = await categoriesAPI.recategorize();
      setRecatMsg(`✅ ${res.changed} transaction(s) recatégorisée(s)`);
    } catch (e) {
      setRecatMsg(`❌ ${(e as Error).message}`);
    }
  };

  return (
    <div className="max-w-4xl">
      <PageTitle
        title="Catégories"
        subtitle="Catégories de flux et règles de catégorisation automatique."
      />

      {error && (
        <p className="mb-4 text-sm text-[var(--neg)]">❌ {error}</p>
      )}
      {loading && (
        <p className="mb-4 text-sm text-[var(--muted)]">Chargement…</p>
      )}

      <div className="flex flex-col gap-5">
        {/* Section Catégories */}
        <Card>
          <div className="mb-4 text-sm font-semibold">Catégories</div>

          {!loading && categories.length === 0 ? (
            <Empty>Aucune catégorie pour le moment.</Empty>
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--border)]">
              {categories.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <span className="text-sm">{c.name}</span>
                  <span className="flex items-center gap-2">
                    {c.is_system && (
                      <Badge tone="neutral">système</Badge>
                    )}
                    <Badge tone={typeTone(c.type)}>{typeLabel(c.type)}</Badge>
                    {!c.is_system && (
                      <button
                        onClick={() => removeCategory(c)}
                        className="text-xs text-[var(--muted)] hover:text-[var(--neg)]"
                        title="Supprimer la catégorie"
                      >
                        🗑️
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-[var(--border)] pt-4">
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Nom</span>
              <input
                type="text"
                value={newCatName}
                onChange={(e) => setNewCatName(e.target.value)}
                placeholder="Nom de la catégorie"
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Type</span>
              <select
                value={newCatType}
                onChange={(e) => setNewCatType(e.target.value as CategoryType)}
                className={inputClass}
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={addCategory} className={btnClass}>
              Ajouter
            </button>
          </div>
        </Card>

        {/* Section Règles */}
        <Card>
          <div className="mb-1 flex items-center justify-between gap-2">
            <div className="text-sm font-semibold">Règles de catégorisation</div>
            <div className="flex items-center gap-2">
              {recatMsg && <span className="text-xs text-[var(--muted)]">{recatMsg}</span>}
              <button
                onClick={reapplyRules}
                className="rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)] hover:bg-[var(--accent)]/10"
                title="Rejoue les règles sur toutes les transactions existantes"
              >
                Ré-appliquer les règles
              </button>
            </div>
          </div>
          <p className="mb-4 text-xs text-[var(--muted)]">
            Les règles s'appliquent par correspondance de sous-chaîne, sans
            tenir compte de la casse. La règle avec le plus petit numéro de
            priorité est évaluée en premier. « Ré-appliquer » les rejoue sur
            l'historique (sinon elles n'agissent qu'à la prochaine synchro).
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                  <th className="py-2 pr-3 font-medium">Champ</th>
                  <th className="py-2 pr-3 font-medium">Motif</th>
                  <th className="py-2 pr-3 font-medium">Catégorie</th>
                  <th className="py-2 pr-3 font-medium">Priorité</th>
                  <th className="py-2 pr-3 font-medium">Actif</th>
                  <th className="py-2 font-medium">Supprimer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {rules.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 pr-3">
                      {FIELD_OPTIONS.find((f) => f.value === r.match_field)
                        ?.label ?? r.match_field}
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        type="text"
                        aria-label={`Motif de la règle ${r.id}`}
                        defaultValue={r.pattern}
                        onBlur={(e) => {
                          const v = e.target.value.trim();
                          if (v && v !== r.pattern) patchRule(r, { pattern: v });
                        }}
                        className={`${inputClass} w-36 font-mono text-xs`}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <select
                        aria-label={`Catégorie de la règle ${r.id}`}
                        value={r.category_id}
                        onChange={(e) =>
                          changeRuleCategory(r, Number(e.target.value))
                        }
                        className={inputClass}
                      >
                        {categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                        {!categories.some((c) => c.id === r.category_id) && (
                          <option value={r.category_id}>
                            {categoryName(r.category_id)}
                          </option>
                        )}
                      </select>
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        type="number"
                        aria-label={`Priorité de la règle ${r.id}`}
                        defaultValue={r.priority}
                        onBlur={(e) => {
                          const v = Number(e.target.value);
                          if (Number.isFinite(v) && v !== r.priority) patchRule(r, { priority: v });
                        }}
                        className={`${inputClass} w-16 tabular`}
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        aria-label={`Activer la règle ${r.id}`}
                        checked={r.enabled}
                        onChange={(e) => toggleRule(r, e.target.checked)}
                      />
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => removeRule(r.id)}
                        className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs text-[var(--neg)] hover:bg-red-50"
                      >
                        Supprimer
                      </button>
                    </td>
                  </tr>
                ))}
                {!loading && rules.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-6 text-center text-[var(--muted)]"
                    >
                      Aucune règle pour le moment.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Formulaire nouvelle règle */}
          <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-[var(--border)] pt-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Champ</span>
              <select
                value={newRuleField}
                onChange={(e) =>
                  setNewRuleField(e.target.value as MatchField)
                }
                className={inputClass}
              >
                {FIELD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Motif</span>
              <input
                type="text"
                value={newRulePattern}
                onChange={(e) => setNewRulePattern(e.target.value)}
                placeholder="ex. stripe"
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Catégorie</span>
              <select
                value={newRuleCategory}
                onChange={(e) =>
                  setNewRuleCategory(
                    e.target.value === '' ? '' : Number(e.target.value),
                  )
                }
                className={inputClass}
              >
                <option value="">— choisir —</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex w-24 flex-col gap-1 text-sm">
              <span className="text-[var(--muted)]">Priorité</span>
              <input
                type="number"
                value={newRulePriority}
                onChange={(e) => setNewRulePriority(e.target.value)}
                className={inputClass}
              />
            </label>
            <button onClick={addRule} className={btnClass}>
              Ajouter
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}
