'use client';

import { useCallback, useEffect, useState } from 'react';
import { bankingAPI } from '@/api/client';
import { PageTitle, Card, Badge, Empty } from '@/components/ui';
import { money, dateFR } from '@/lib/format';

type Status = { live: boolean; message: string };
type Aspsp = { name: string; country?: string };
type Connection = {
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
  transactions_added: number;
  transactions_skipped: number;
};

export default function BankingPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [aspsps, setAspsps] = useState<Aspsp[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  const [authUrl, setAuthUrl] = useState<string>('');
  const [connecting, setConnecting] = useState<string>('');
  const [code, setCode] = useState<string>('');
  const [callbackMsg, setCallbackMsg] = useState<string>('');

  const [syncing, setSyncing] = useState(false);
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

  const handleConnect = async (name: string) => {
    setConnecting(name);
    setAuthUrl('');
    setCallbackMsg('');
    setError('');
    try {
      const res = await bankingAPI.connect(name);
      setAuthUrl(res.authorization_url as string);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConnecting('');
    }
  };

  const handleCallback = async () => {
    if (!code.trim()) return;
    setCallbackMsg('Validation…');
    setError('');
    try {
      const accounts = await bankingAPI.createSession(code.trim());
      const n = Array.isArray(accounts) ? accounts.length : 0;
      setCallbackMsg(`✅ Session créée — ${n} compte(s) rattaché(s)`);
      setCode('');
      await loadConnections();
    } catch (e) {
      setCallbackMsg('');
      setError((e as Error).message);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncMsg('');
    setError('');
    try {
      const res = (await bankingAPI.sync()) as SyncResult;
      setSyncMsg(
        `✅ ${res.accounts_synced} compte(s), ${res.transactions_added} transaction(s) ajoutée(s), ${res.transactions_skipped} ignorée(s)`,
      );
      await loadConnections();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <PageTitle
        title="Banques"
        subtitle="Connexion Open Banking (Enable Banking) & synchronisation"
        action={
          <button
            onClick={handleSync}
            disabled={syncing || loading}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {syncing ? 'Synchronisation…' : 'Synchroniser'}
          </button>
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
