'use client';

import { useCallback, useEffect, useState } from 'react';
import { bankingAPI } from '@/api/client';
import { BalanceDocsModal } from '@/components/BalanceDocsModal';
import ImportCsvCard from '@/components/ImportCsvCard';
import { MonthlyReconcileCard } from '@/components/MonthlyReconcileCard';
import { PageTitle, Card, Badge, Empty } from '@/components/ui';
import { money, dateFR } from '@/lib/format';

type Status = { live: boolean; message: string };
type Aspsp = { name: string; country?: string };
type Connection = {
  id: number;
  account_uid: string;
  name: string;
  provider: string;
  currency: string;
  iban_masked: string;
  balance: number | string;
  last_synced_at: string | null;
};
type SyncResult = {
  accounts_synced: number;
  accounts_total: number;
  transactions_added: number;
  transactions_skipped: number;
  transactions_categorized: number;
  invoices_reconciled: number;
  errors: { account_uid: string; error: string }[];
};
type AccountPreview = {
  account_uid: string;
  provider: string;
  currency: string;
  iban_masked: string;
  name: string;
};

export default function BankingPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [aspsps, setAspsps] = useState<Aspsp[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  const [authUrl, setAuthUrl] = useState<string>('');
  const [authState, setAuthState] = useState<string>(''); // state OAuth émis (anti-CSRF)
  const [connecting, setConnecting] = useState<string>('');
  const [code, setCode] = useState<string>('');
  const [callbackMsg, setCallbackMsg] = useState<string>('');

  // Étape de sélection : comptes disponibles après échange du code.
  const [available, setAvailable] = useState<AccountPreview[] | null>(null);
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [attaching, setAttaching] = useState(false);

  const [syncing, setSyncing] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string>('');

  const loadConnections = useCallback(async () => {
    const conns = await bankingAPI.connections();
    setConnections(conns as Connection[]);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [st, banks, conns] = await Promise.all([
          bankingAPI.status(),
          bankingAPI.aspsps('FR'),
          bankingAPI.connections(),
        ]);
        if (!alive) return;
        setStatus(st);
        setAspsps(banks as Aspsp[]);
        setConnections(conns as Connection[]);
      } catch (e) {
        if (alive) setError((e as Error).message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Scroll vers l'ancre visée par l'URL une fois le chargement terminé.
  // Sur une navigation client-side (ex: lien du dashboard vers /banking#rappro-mensuel),
  // Next.js tente de scroller vers l'ancre immédiatement après la navigation — trop tôt,
  // le contenu est encore sous la garde `loading` et l'élément n'existe pas dans le DOM.
  // Cet effet reprend le scroll une fois le contenu réellement monté.
  useEffect(() => {
    if (loading) return;
    if (typeof window === 'undefined') return;
    const hash = window.location.hash;
    if (!hash || hash.length <= 1) return;
    const id = decodeURIComponent(hash.slice(1));
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView();
    }
  }, [loading]);

  const handleConnect = async (name: string) => {
    setConnecting(name);
    setAuthUrl('');
    setCallbackMsg('');
    setAvailable(null);
    setError('');
    try {
      const res = await bankingAPI.connect(name);
      setAuthUrl(res.authorization_url as string);
      setAuthState((res.state as string) ?? '');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConnecting('');
    }
  };

  // Étape 1 : échange du code → liste des comptes disponibles (rien de rattaché).
  const handleCallback = async () => {
    if (!code.trim()) return;
    setCallbackMsg('Récupération des comptes…');
    setError('');
    try {
      const res = await bankingAPI.createSession(code.trim(), authState || undefined);
      const accounts = (res.accounts ?? []) as AccountPreview[];
      setAvailable(accounts);
      // Tout coché par défaut : l'utilisateur décoche ce qu'il ne veut pas.
      setChosen(Object.fromEntries(accounts.map((a) => [a.account_uid, true])));
      setCallbackMsg(`${accounts.length} compte(s) disponible(s) — choisissez ceux à rattacher.`);
    } catch (e) {
      setCallbackMsg('');
      setError((e as Error).message);
    }
  };

  // Étape 2 : rattache uniquement les comptes cochés.
  const handleAttach = async () => {
    if (!available) return;
    const picked = available.filter((a) => chosen[a.account_uid]);
    if (picked.length === 0) {
      setError('Sélectionnez au moins un compte à rattacher.');
      return;
    }
    setAttaching(true);
    setError('');
    try {
      await bankingAPI.selectAccounts(picked as unknown as Record<string, unknown>[]);
      setCallbackMsg(`✅ ${picked.length} compte(s) rattaché(s)`);
      setAvailable(null);
      setCode('');
      setAuthUrl('');
      setAuthState('');
      await loadConnections();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAttaching(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncMsg('');
    setError('');
    try {
      const res = (await bankingAPI.sync()) as SyncResult;
      const nErr = res.errors?.length ?? 0;
      let msg = `✅ ${res.accounts_synced}/${res.accounts_total ?? res.accounts_synced} compte(s), ${res.transactions_added} ajoutée(s), ${res.transactions_skipped} ignorée(s), ${res.transactions_categorized ?? 0} catégorisée(s), ${res.invoices_reconciled ?? 0} rapprochée(s)`;
      if (nErr > 0) {
        msg += ` — ⚠️ ${nErr} compte(s) en échec (reconnexion requise) : ${res.errors.map((e) => e.account_uid).join(', ')}`;
      }
      setSyncMsg(msg);
      await loadConnections();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async (c: Connection) => {
    if (!confirm(`Déconnecter le compte « ${c.name || c.account_uid} » ? Les transactions déjà importées sont conservées.`)) return;
    try {
      await bankingAPI.disconnect(c.id);
      await loadConnections();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="max-w-4xl">
      <PageTitle
        title="Banques"
        subtitle="Connexion Open Banking (Enable Banking) & synchronisation"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDocsOpen(true)}
              className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-medium hover:border-[var(--accent)]"
              title="Justificatifs de solde (relevés) par compte"
            >
              📎 Justificatifs
            </button>
            <button
              onClick={handleSync}
              disabled={syncing || loading}
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {syncing ? 'Synchronisation…' : 'Synchroniser'}
            </button>
          </div>
        }
      />

      {error && (
        <p className="mb-4 text-sm text-[var(--neg)]">❌ {error}</p>
      )}
      {syncMsg && (
        <p className="mb-4 text-sm text-[var(--muted)]">{syncMsg}</p>
      )}

      {loading ? (
        <p className="text-sm text-[var(--muted)]">Chargement…</p>
      ) : (
        <div className="flex flex-col gap-5">
          {/* Statut du connecteur */}
          <Card>
            <div className="mb-3 flex items-center gap-2">
              <span className="text-sm font-semibold">Statut</span>
              {status &&
                (status.live ? (
                  <Badge tone="pos">Connecté</Badge>
                ) : (
                  <Badge tone="warn">Mode démo</Badge>
                ))}
            </div>
            <p className="text-sm text-[var(--muted)]">
              {status?.message ?? '—'}
            </p>
            {status && !status.live && (
              <p className="mt-2 text-xs text-[var(--muted)]">
                Renseigner <code>ENABLE_BANKING_APP_ID</code> et la clé PEM pour
                passer en mode réel.
              </p>
            )}
          </Card>

          {/* Connexion d'une banque */}
          <Card>
            <div className="mb-3 text-sm font-semibold">
              Connecter une banque
            </div>
            {aspsps.length === 0 ? (
              <Empty>Aucune banque disponible.</Empty>
            ) : (
              <div className="flex flex-wrap gap-2">
                {aspsps.map((b) => (
                  <button
                    key={b.name}
                    onClick={() => handleConnect(b.name)}
                    disabled={connecting === b.name}
                    className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)] disabled:opacity-50"
                  >
                    {connecting === b.name ? 'Connexion…' : b.name}
                  </button>
                ))}
              </div>
            )}

            {authUrl && (
              <div className="mt-4 rounded-lg border border-dashed border-[var(--border)] p-3 text-sm">
                <div className="mb-1 text-[var(--muted)]">
                  URL d&apos;autorisation :
                </div>
                <a
                  href={authUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all text-[var(--accent)] underline"
                >
                  {authUrl}
                </a>
                <p className="mt-2 text-xs text-[var(--muted)]">
                  En mode démo, cette URL est simulée. Collez le code renvoyé
                  ci-dessous pour simuler le retour.
                </p>
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--muted)]">
                  Code de retour (callback)
                </span>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="code…"
                  className="rounded-lg border border-[var(--border)] px-3 py-2 outline-none focus:border-[var(--accent)]"
                />
              </label>
              <button
                onClick={handleCallback}
                disabled={!code.trim()}
                className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)] disabled:opacity-50"
              >
                Valider le code
              </button>
              {callbackMsg && (
                <span className="text-sm text-[var(--muted)]">
                  {callbackMsg}
                </span>
              )}
            </div>

            {/* Étape de sélection des comptes à rattacher */}
            {available && (
              <div className="mt-4 rounded-lg border border-[var(--border)] p-3">
                <div className="mb-2 text-sm font-semibold">
                  Comptes disponibles — sélectionnez à rattacher
                </div>
                {available.length === 0 ? (
                  <Empty>Aucun compte disponible pour cette connexion.</Empty>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    {available.map((a) => (
                      <label
                        key={a.account_uid}
                        className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-black/[0.02]"
                      >
                        <input
                          type="checkbox"
                          checked={!!chosen[a.account_uid]}
                          onChange={(e) =>
                            setChosen((prev) => ({ ...prev, [a.account_uid]: e.target.checked }))
                          }
                        />
                        <span className="flex-1">
                          <b>{a.name || a.account_uid}</b>{' '}
                          <span className="text-[var(--muted)]">
                            · {a.provider} · {a.currency} · {a.iban_masked}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={handleAttach}
                    disabled={attaching || available.length === 0}
                    className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                  >
                    {attaching ? 'Rattachement…' : 'Rattacher les comptes sélectionnés'}
                  </button>
                  <button
                    onClick={() => setAvailable(null)}
                    className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)]"
                  >
                    Annuler
                  </button>
                </div>
              </div>
            )}
          </Card>

          {/* Comptes connectés */}
          <Card>
            <div className="mb-3 text-sm font-semibold">Comptes connectés</div>
            {connections.length === 0 ? (
              <Empty>Aucun compte connecté pour le moment.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                      <th className="py-2 pr-4 font-medium">Nom</th>
                      <th className="py-2 pr-4 font-medium">Provider</th>
                      <th className="py-2 pr-4 font-medium">Devise</th>
                      <th className="py-2 pr-4 font-medium">IBAN</th>
                      <th className="py-2 pr-4 text-right font-medium">Solde</th>
                      <th className="py-2 pr-4 font-medium">
                        Dernière synchro
                      </th>
                      <th className="py-2 font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections.map((c) => (
                      <tr
                        key={c.account_uid}
                        className="border-b border-[var(--border)] last:border-0"
                      >
                        <td className="py-2 pr-4">{c.name}</td>
                        <td className="py-2 pr-4">
                          <Badge>{c.provider}</Badge>
                        </td>
                        <td className="py-2 pr-4">{c.currency}</td>
                        <td className="tabular py-2 pr-4">{c.iban_masked}</td>
                        <td className="tabular py-2 pr-4 text-right">
                          {money(c.balance, c.currency)}
                        </td>
                        <td className="py-2 pr-4">
                          {dateFR(c.last_synced_at)}
                        </td>
                        <td className="py-2 text-right">
                          <button
                            onClick={() => handleDisconnect(c)}
                            className="text-xs text-[var(--muted)] hover:text-[var(--neg)]"
                            title="Déconnecter ce compte"
                          >
                            Déconnecter
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Rapprochement mensuel officiel — cible du lien « Déposer un relevé → »
              de la carte Soldes bancaires du dashboard. `scroll-mt-20` dégage la
              barre de nav mobile fixe (Nav.tsx) à l'arrivée sur l'ancre. */}
          <div id="rappro-mensuel" className="scroll-mt-20">
            <MonthlyReconcileCard year={new Date().getFullYear()} />
          </div>

          {/* Import CSV — historique bancaire */}
          <div>
            <div className="mb-3 text-sm font-semibold">
              Import CSV — historique bancaire
            </div>
            <ImportCsvCard />
          </div>
        </div>
      )}
          {docsOpen && <BalanceDocsModal onClose={() => setDocsOpen(false)} />}
    </div>
  );
}
