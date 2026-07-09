"""
Service Enable Banking — auth JWT, connexion OAuth, sync transactions.

Principe fondamental : l'application DOIT tourner (et les tests passer) même
SANS identifiants ni réseau. On construit donc un « seam » propre :

- Si `settings.enable_banking_app_id` est vide, OU le fichier clé privée est
  absent, OU `pyjwt` n'est pas installé → **mode MOCK** : données d'exemple
  déterministes, aucun appel réseau.
- Sinon → **mode LIVE** : vrais appels httpx signés RS256.

`is_live()` expose l'état courant.

Convention dedup : la clé d'unicité est **(account_uid, external_id)** — jamais
`external_id` seul (les trades FX Revolut partagent un transaction_id entre les
deux comptes de l'échange).

Ne jamais logger : IBAN, clés, secrets.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from fastapi import HTTPException

from backend.config import settings
from backend.db import models
from backend.logging_config import get_logger

logger = get_logger("banking", channel="api")

# ---------------------------------------------------------------------------
# Constantes Enable Banking
# ---------------------------------------------------------------------------

_API_BASE = "https://api.enablebanking.com"
_JWT_ISS = "enablebanking.com"
_JWT_AUD = "api.enablebanking.com"
_ACCESS_VALIDITY_DAYS = 90
_HTTP_TIMEOUT = 30.0

# États OAuth émis en attente de retour (anti-CSRF). Stockés en mémoire : le
# flux connect → autorisation → callback dure quelques minutes, le serveur local
# reste allumé. Un redémarrage force une reconnexion (acceptable en mono-poste).
_pending_states: set[str] = set()


def _register_state(state: str) -> None:
    """Mémorise un state émis (borne de sécurité : cap souple pour éviter la fuite)."""
    if len(_pending_states) > 64:
        _pending_states.clear()
    _pending_states.add(state)


def _verify_state(state: Optional[str]) -> None:
    """
    Vérifie le state OAuth renvoyé au callback (anti-CSRF), puis le consomme.

    Live : state **obligatoire** et doit correspondre à un state émis → sinon 400.
    Mock : vérifié si fourni (consommé), sinon toléré (tests directs du service).
    """
    if not is_live():
        if state:
            _pending_states.discard(state)
        return
    if not state or state not in _pending_states:
        raise HTTPException(
            status_code=400,
            detail="État OAuth invalide ou expiré — relancez la connexion à la banque",
        )
    _pending_states.discard(state)


# ---------------------------------------------------------------------------
# Détection du mode (live vs mock)
# ---------------------------------------------------------------------------

def _pyjwt():
    """Import paresseux de pyjwt. Retourne le module ou None si absent."""
    try:
        import jwt  # type: ignore

        return jwt
    except Exception:  # ImportError et compagnie
        return None


def _key_path() -> Path:
    return Path(settings.enable_banking_private_key_path)


def _load_private_key() -> str:
    """
    Lit la clé privée et renvoie un PEM valide, quel que soit le format stocké.

    Accepte :
    - un PEM complet (`-----BEGIN … PRIVATE KEY-----` avec retours à la ligne) ;
    - un corps base64 brut (cas Railway/Vercel : en-têtes et newlines supprimés).
      On reconstruit alors le PEM (headers + lignes de 64 caractères).
    Voir docs/integrations/enablebanking.md (gotcha « Railway strips newlines »).
    """
    import textwrap

    raw = _key_path().read_text(encoding="utf-8").replace("\\n", "\n").strip()
    if raw.startswith("-----BEGIN"):
        return raw
    body = "".join(raw.split())  # retire tout espace/newline résiduel
    wrapped = "\n".join(textwrap.wrap(body, 64))
    return f"-----BEGIN PRIVATE KEY-----\n{wrapped}\n-----END PRIVATE KEY-----\n"


def is_live() -> bool:
    """
    True si l'on peut réellement appeler Enable Banking :
    app_id présent, fichier clé lisible, pyjwt disponible.
    """
    if not settings.enable_banking_app_id:
        return False
    if not _key_path().is_file():
        return False
    if _pyjwt() is None:
        return False
    return True


def status() -> dict[str, Any]:
    """État lisible du service (pour l'endpoint /status)."""
    live = is_live()
    if live:
        # Honnêteté : « live » ne signifie que « creds présents », pas que les
        # consentements bancaires (90 j) sont valides — ça se vérifie à la synchro.
        message = "Enable Banking en mode live — la validité des consentements est vérifiée à la synchro."
    else:
        reasons = []
        if not settings.enable_banking_app_id:
            reasons.append("app_id manquant")
        elif not _key_path().is_file():
            reasons.append("clé privée introuvable")
        elif _pyjwt() is None:
            reasons.append("pyjwt non installé")
        message = "Mode démo (mock) — " + ", ".join(reasons) + "."
    return {"live": live, "message": message}


# ---------------------------------------------------------------------------
# Auth JWT (mode live uniquement)
# ---------------------------------------------------------------------------

def _make_jwt() -> str:
    """
    Génère un JWT RS256 frais (expiry ≤ 1h) signé avec la clé privée.
    Header kid = App ID. Appelé uniquement en mode live.
    """
    jwt = _pyjwt()
    if jwt is None:  # garde-fou : ne devrait pas arriver en live
        raise RuntimeError("pyjwt indisponible")

    now = int(datetime.now(tz=timezone.utc).timestamp())
    payload = {
        "iss": _JWT_ISS,
        "aud": _JWT_AUD,
        "iat": now,
        "exp": now + 3600,
    }
    private_key = _load_private_key()
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": settings.enable_banking_app_id},
    )


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_jwt()}"}


# ---------------------------------------------------------------------------
# Normalisation d'une transaction (partagée live / mock)
# ---------------------------------------------------------------------------

def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _resolve_external_id(raw: dict[str, Any]) -> str:
    """external_id (ordre de priorité Enable Banking)."""
    return (
        raw.get("transaction_id")
        or raw.get("entry_reference")
        or raw.get("internal_transaction_id")
        or ""
    )


def _signed_amount(raw: dict[str, Any]) -> Decimal:
    """Signe le montant : DBIT → négatif, CRDT → positif."""
    amt = Decimal(str(raw.get("transaction_amount", {}).get("amount", "0")))
    indicator = raw.get("credit_debit_indicator", "DBIT")
    if indicator == "DBIT":
        return -abs(amt)
    return abs(amt)


def _counterparty(raw: dict[str, Any]) -> str:
    """Nom de la contrepartie (créditeur ou débiteur selon le sens)."""
    for key in ("creditor", "debtor"):
        node = raw.get(key)
        if isinstance(node, dict) and node.get("name"):
            return node["name"]
    return raw.get("counterparty", "")


def _description(raw: dict[str, Any]) -> str:
    info = raw.get("remittance_information")
    if isinstance(info, list):
        return " ".join(str(i) for i in info if i)
    if isinstance(info, str):
        return info
    return raw.get("description", "")


def _normalize_txn(raw: dict[str, Any], account: models.BankAccount) -> dict[str, Any]:
    """Transforme une transaction brute Enable Banking en champs Transaction."""
    amount_currency = raw.get("transaction_amount", {}).get("currency") or account.currency
    return {
        "account_uid": account.account_uid,
        "external_id": _resolve_external_id(raw),
        "booked_date": _parse_date(raw.get("booking_date")),
        "value_date": _parse_date(raw.get("value_date")),
        "amount": _signed_amount(raw),
        "currency": amount_currency,
        "description": _description(raw),
        "counterparty": _counterparty(raw),
        "raw_json": json.dumps(raw, ensure_ascii=False, sort_keys=True),
    }


# ---------------------------------------------------------------------------
# Données MOCK déterministes
# ---------------------------------------------------------------------------

_MOCK_ASPSPS = [
    {"name": "Revolut Business", "country": "FR"},
    {"name": "Qonto", "country": "FR"},
    {"name": "BNP Paribas", "country": "FR"},
    {"name": "Boursorama", "country": "FR"},
]

# Comptes renvoyés par une session mock.
_MOCK_ACCOUNTS = [
    {
        "uid": "mock-revolut-eur",
        "aspsp": "Revolut Business",
        "currency": "EUR",
        "iban_masked": "FR76****01",
        "name": "Revolut Business EUR",
    },
    {
        "uid": "mock-qonto-eur",
        "aspsp": "Qonto",
        "currency": "EUR",
        "iban_masked": "FR76****42",
        "name": "Qonto Courant",
    },
]


def _mock_raw_transactions(account_uid: str) -> list[dict[str, Any]]:
    """Transactions brutes déterministes pour un compte (format Enable Banking)."""
    if account_uid == "mock-revolut-eur":
        return [
            {
                "transaction_id": "rev-tx-001",
                "booking_date": "2026-01-15",
                "value_date": "2026-01-15",
                "transaction_amount": {"amount": "5400.00", "currency": "EUR"},
                "credit_debit_indicator": "CRDT",
                "remittance_information": ["Invoice SWIB 2026-01"],
                "debtor": {"name": "SWIB LLC"},
            },
            {
                "transaction_id": "rev-tx-002",
                "booking_date": "2026-01-20",
                "value_date": "2026-01-20",
                "transaction_amount": {"amount": "89.90", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "remittance_information": ["AWS EU cloud"],
                "creditor": {"name": "Amazon Web Services"},
            },
            {
                # Trade FX : même transaction_id que la jambe Qonto ci-dessous.
                "transaction_id": "fx-shared-777",
                "booking_date": "2026-02-03",
                "value_date": "2026-02-03",
                "transaction_amount": {"amount": "1000.00", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "remittance_information": ["FX EUR->CAD leg"],
                "creditor": {"name": "Revolut FX"},
            },
        ]
    if account_uid == "mock-qonto-eur":
        return [
            {
                "transaction_id": "qon-tx-001",
                "booking_date": "2026-01-10",
                "value_date": "2026-01-10",
                "transaction_amount": {"amount": "3200.00", "currency": "EUR"},
                "credit_debit_indicator": "CRDT",
                "remittance_information": ["Invoice NWH 2026-01"],
                "debtor": {"name": "NWH Inc"},
            },
            {
                "transaction_id": "qon-tx-002",
                "booking_date": "2026-01-25",
                "value_date": "2026-01-25",
                "transaction_amount": {"amount": "450.00", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "remittance_information": ["URSSAF cotisations"],
                "creditor": {"name": "URSSAF"},
            },
            {
                # Même transaction_id que la jambe Revolut : NE doit PAS être
                # dédupliqué (compte différent).
                "transaction_id": "fx-shared-777",
                "booking_date": "2026-02-03",
                "value_date": "2026-02-03",
                "transaction_amount": {"amount": "1450.00", "currency": "CAD"},
                "credit_debit_indicator": "CRDT",
                "remittance_information": ["FX EUR->CAD leg"],
                "debtor": {"name": "Revolut FX"},
            },
        ]
    return []


def _provider_for_aspsp(aspsp_name: str) -> str:
    """Déduit le provider interne ('revolut'|'qonto'|slug) depuis le nom ASPSP."""
    low = aspsp_name.lower()
    if "revolut" in low:
        return "revolut"
    if "qonto" in low:
        return "qonto"
    return low.replace(" ", "-")


# ---------------------------------------------------------------------------
# HTTP live helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    import httpx

    with httpx.Client(base_url=_API_BASE, timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(path, params=params, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    with httpx.Client(base_url=_API_BASE, timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(path, json=body, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# API publique du service
# ---------------------------------------------------------------------------

def list_aspsps(country: str = "FR") -> list[dict[str, Any]]:
    """Liste des banques (ASPSP) disponibles pour un pays."""
    if not is_live():
        logger.info("📤 [Banking] list_aspsps (mock): pays=%s", country)
        return [a for a in _MOCK_ASPSPS if a["country"] == country]

    logger.info("📥 [Banking] list_aspsps (live): pays=%s", country)
    data = _get("/aspsps", params={"country": country})
    return [
        {"name": a.get("name", ""), "country": a.get("country", country)}
        for a in data.get("aspsps", [])
    ]


def start_auth(aspsp_name: str, country: str = "FR") -> dict[str, Any]:
    """
    Démarre l'autorisation OAuth : renvoie {authorization_url, state}.
    L'utilisateur est ensuite redirigé vers cette URL (site de la banque).
    Le `state` est mémorisé côté serveur pour être revérifié au callback (CSRF).
    """
    state = str(uuid.uuid4())
    _register_state(state)

    if not is_live():
        logger.info("📤 [Banking] start_auth (mock): aspsp=%s", aspsp_name)
        url = (
            f"{settings.enable_banking_redirect_url}"
            f"?mock=1&aspsp={aspsp_name.replace(' ', '+')}&state={state}"
        )
        return {"authorization_url": url, "state": state}

    from datetime import timedelta

    valid_until_iso = (
        datetime.now(tz=timezone.utc) + timedelta(days=_ACCESS_VALIDITY_DAYS)
    ).isoformat()
    body = {
        "access": {"valid_until": valid_until_iso},
        "aspsp": {"name": aspsp_name, "country": country},
        "state": state,
        "redirect_url": settings.enable_banking_redirect_url,
        "psu_type": "business",
    }
    logger.info("📥 [Banking] start_auth (live): aspsp=%s", aspsp_name)
    data = _post("/auth", body)
    return {"authorization_url": data.get("url", ""), "state": state}


def _upsert_account(
    db: Session,
    *,
    account_uid: str,
    provider: str,
    currency: str,
    iban_masked: str,
    name: str,
) -> models.BankAccount:
    """Crée ou met à jour un BankAccount (jamais de doublon sur account_uid)."""
    existing = (
        db.query(models.BankAccount)
        .filter(models.BankAccount.account_uid == account_uid)
        .one_or_none()
    )
    if existing is not None:
        existing.provider = provider
        existing.currency = currency
        existing.iban_masked = iban_masked
        existing.name = name
        return existing

    acc = models.BankAccount(
        account_uid=account_uid,
        provider=provider,
        currency=currency,
        iban_masked=iban_masked,
        name=name,
        balance=Decimal("0"),
    )
    db.add(acc)
    return acc


def create_session(
    db: Session, code: str, state: Optional[str] = None
) -> dict[str, Any]:
    """
    Échange le code d'autorisation contre une session + la **liste des comptes
    disponibles** (aperçu, non persistée).

    Le code OAuth étant à usage unique, l'échange n'a lieu qu'ici : l'utilisateur
    choisit ensuite les comptes à rattacher via `select_accounts`. Vérifie le
    `state` (anti-CSRF) avant l'échange.

    Chaque compte de l'aperçu : {account_uid, provider, currency, iban_masked, name}.
    """
    _verify_state(state)

    if not is_live():
        logger.info("📤 [Banking] create_session (mock)")
        previews = [
            {
                "account_uid": spec["uid"],
                "provider": _provider_for_aspsp(spec["aspsp"]),
                "currency": spec["currency"],
                "iban_masked": spec["iban_masked"],
                "name": spec["name"],
            }
            for spec in _MOCK_ACCOUNTS
        ]
        return {"session_id": "mock-session", "accounts": previews}

    logger.info("📥 [Banking] create_session (live)")
    data = _post("/sessions", {"code": code})
    aspsp_name = data.get("aspsp", {}).get("name", "")
    provider = _provider_for_aspsp(aspsp_name)
    previews = [
        {
            "account_uid": raw.get("uid", ""),
            "provider": provider,
            "currency": raw.get("currency", "EUR"),
            "iban_masked": _mask_iban(raw.get("account_id", {}).get("iban", "")),
            "name": raw.get("name", "") or raw.get("product", ""),
        }
        for raw in data.get("accounts", [])
    ]
    return {"session_id": data.get("session_id", ""), "accounts": previews}


def select_accounts(
    db: Session, accounts: list[dict[str, Any]]
) -> list[models.BankAccount]:
    """
    Rattache (persiste) les comptes **choisis** par l'utilisateur à l'issue de
    `create_session`. Chaque item : {account_uid, provider, currency,
    iban_masked, name}. Upsert idempotent sur `account_uid`.
    """
    out: list[models.BankAccount] = []
    for a in accounts:
        if not a.get("account_uid"):
            continue
        acc = _upsert_account(
            db,
            account_uid=a["account_uid"],
            provider=a.get("provider", ""),
            currency=a.get("currency", "EUR"),
            iban_masked=a.get("iban_masked", ""),
            name=a.get("name", ""),
        )
        out.append(acc)
    db.commit()
    for acc in out:
        db.refresh(acc)
    logger.info("📤 [Banking] select_accounts: %d compte(s) rattaché(s) ✅", len(out))
    return out


def _mask_iban(iban: str) -> str:
    if not iban:
        return ""
    return iban[:4] + "****" + iban[-2:]


def _fetch_raw_transactions(account: models.BankAccount) -> list[dict[str, Any]]:
    """Récupère les transactions brutes d'un compte (live paginé ou mock)."""
    if not is_live():
        return _mock_raw_transactions(account.account_uid)

    transactions: list[dict[str, Any]] = []
    params: dict[str, Any] = {"date_from": "2026-01-01"}
    while True:
        data = _get(f"/accounts/{account.account_uid}/transactions", params=params)
        transactions.extend(data.get("transactions", []))
        cont = data.get("continuation_key")
        if not cont:
            break
        params["continuation_key"] = cont
    return transactions


def _fetch_balance(account: models.BankAccount) -> Optional[Decimal]:
    """Récupère le solde courant d'un compte (live), ou None (mock → calculé)."""
    if not is_live():
        return None
    data = _get(f"/accounts/{account.account_uid}/balances")
    balances = data.get("balances", [])
    if not balances:
        return None
    amt = balances[0].get("balance_amount", {}).get("amount")
    return Decimal(str(amt)) if amt is not None else None


def sync(db: Session) -> dict[str, Any]:
    """
    Synchronise tous les comptes : récupère les transactions, déduplique sur
    (account_uid, external_id), signe les montants, met à jour solde et
    last_synced_at.

    Retourne {accounts_synced, transactions_added, transactions_skipped}.
    """
    accounts = db.query(models.BankAccount).all()
    added = 0
    skipped = 0
    synced = 0
    errors: list[dict] = []

    for account in accounts:
        # Chaque compte est isolé par un SAVEPOINT : une erreur (ex. consentement
        # expiré → 401) n'avorte PAS toute la synchro ni les comptes déjà traités —
        # seul le compte en échec est annulé, on le note et on passe au suivant.
        added_before, skipped_before = added, skipped
        try:
            with db.begin_nested():
                # IDs déjà présents pour ce compte (dedup (account_uid, external_id)).
                existing_ids = {
                    row[0]
                    for row in db.query(models.Transaction.external_id)
                    .filter(models.Transaction.account_uid == account.account_uid)
                    .all()
                }

                raw_txns = _fetch_raw_transactions(account)
                seen_this_run: set[str] = set()

                for raw in raw_txns:
                    norm = _normalize_txn(raw, account)
                    ext_id = norm["external_id"]
                    if not ext_id:
                        skipped += 1
                        continue
                    if ext_id in existing_ids or ext_id in seen_this_run:
                        skipped += 1
                        continue
                    seen_this_run.add(ext_id)
                    db.add(models.Transaction(**norm))
                    added += 1

                # Solde : live → API ; mock → opening_balance + somme des transactions.
                balance = _fetch_balance(account)
                if balance is None:
                    total = (
                        db.query(models.Transaction)
                        .filter(models.Transaction.account_uid == account.account_uid)
                        .all()
                    )
                    balance = account.opening_balance + sum(
                        (t.amount for t in total), Decimal("0")
                    )
                account.balance = balance
                account.last_synced_at = datetime.now(tz=timezone.utc)
            synced += 1
        except Exception as exc:  # noqa: BLE001 — on isole chaque compte
            added, skipped = added_before, skipped_before  # compteurs annulés avec le savepoint
            msg = str(exc) or exc.__class__.__name__
            logger.warning(
                "⚠️ [Banking] sync: compte %s en échec (%s) — reconnexion requise ?",
                account.account_uid,
                msg,
            )
            errors.append({"account_uid": account.account_uid, "error": msg})

    # Re-catégorisation automatique des nouvelles écritures (spec S3.3).
    db.flush()  # rendre les transactions ajoutées visibles au moteur de règles
    from backend.services.categorize import recategorize_all

    categorized = recategorize_all(db)
    db.commit()

    # Rapprochement auto des paiements importés avec les factures ouvertes : ferme
    # la boucle accrual (une transaction rattachée `invoice_id` est exclue du P&L,
    # la facture la comptant déjà côté mois travaillé → pas de double comptage).
    from backend.services.invoices import reconcile_payments

    reconciled = reconcile_payments(db)

    # Reconstitue le taux FX RÉELLEMENT obtenu (conversions Revolut appariées) et
    # le propage aux factures payées : `amount_eur_received` = vrai EUR encaissé,
    # jamais le montant natif pris pour des euros (cf. services/fx_realized).
    from backend.services.fx_realized import allocate as allocate_fx_realized

    allocate_fx_realized(db)
    logger.info(
        "✅ [Banking] sync: comptes=%d/%d ajoutées=%d ignorées=%d catégorisées=%d "
        "rapprochées=%d erreurs=%d",
        synced,
        len(accounts),
        added,
        skipped,
        categorized,
        reconciled,
        len(errors),
    )
    return {
        "accounts_synced": synced,
        "accounts_total": len(accounts),
        "transactions_added": added,
        "transactions_skipped": skipped,
        "transactions_categorized": categorized,
        "invoices_reconciled": reconciled,
        "errors": errors,
    }


def disconnect_account(db: Session, account_id: int) -> bool:
    """
    Déconnecte (supprime) un compte bancaire. Retourne False s'il n'existe pas.

    Les transactions déjà importées sont conservées (historique) ; seul le compte
    disparaît de la liste et cesse d'être synchronisé / compté dans la trésorerie.
    """
    account = db.get(models.BankAccount, account_id)
    if account is None:
        return False
    db.delete(account)
    db.commit()
    logger.info("🗑️ [Banking] disconnect: compte id=%d (%s) ✅", account_id, account.account_uid)
    return True
