"""
Service Factures LGC — numérotation, rendu HTML/PDF, rapprochement paiements.

Règles métier :
- Numérotation : `Settings.next_invoice_number` (entier), formaté en chaîne.
  L'incrément n'a lieu QUE lors de la création effective d'une facture.
- Montant : `amount = hours * rate` (toujours en `Decimal`, jamais float).
- PDF : WeasyPrint dépend de libs système (pango/cairo). Import PARESSEUX,
  gardé par try/except → HTTPException(503) si indisponible. Les tests ne
  doivent jamais dépendre de WeasyPrint (on teste le HTML séparément).
- Rapprochement : on relie une facture non payée ('draft'/'sent') à une
  transaction bancaire de revenu dont le montant matche (tolérance) et dont la
  contrepartie/description contient le `counterparty_match` du client.

Détermination : `create_invoice` accepte `issue_date` (défaut = aujourd'hui si
None) pour rester déterministe en test.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import fx

logger = get_logger("invoices", channel="backend")

# Délai de paiement par défaut : échéance = fin du mois de service + N jours.
_DEFAULT_TERMS = 45


def _period_end(month: str) -> date:
    """Dernier jour du mois de service 'YYYY-MM'."""
    y, m = int(month[:4]), int(month[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


def _term_days(client: Optional[models.Client]) -> int:
    """Délai de paiement du client (jours), repli sur le défaut métier."""
    return client.payment_terms_days if client and client.payment_terms_days else _DEFAULT_TERMS

# Racine projet (…/compta_sasu) : base.py utilise parents[2], on fait pareil.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_INVOICES_DIR = _PROJECT_ROOT / "data" / "invoices"

# Tolérance de rapprochement montant (valeur absolue, même devise).
_RECONCILE_TOLERANCE = Decimal("0.01")

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _fr_amount(value) -> str:
    """Montant au format français : 18240 → '18 240,00' (espace milliers, virgule)."""
    return f"{Decimal(value or 0):,.2f}".replace(",", " ").replace(".", ",")


_jinja_env.filters["fr"] = _fr_amount


def _get_settings(db: Session) -> models.Settings:
    """Retourne la ligne Settings singleton (id=1), en la créant si absente."""
    row = db.get(models.Settings, 1)
    if row is None:
        row = models.Settings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("🗄️ [Invoices] settings: ligne singleton créée")
    return row


def next_number(db: Session) -> str:
    """
    Retourne le prochain numéro de facture (chaîne) SANS incrémenter.

    Lecture seule : sert à l'affichage / prévisualisation.
    """
    settings = _get_settings(db)
    return str(settings.next_invoice_number)


def create_invoice(db: Session, data: dict, issue_date: Optional[date] = None) -> models.Invoice:
    """
    Crée une facture 'draft' et incrémente le compteur de numérotation.

    `data` attend : client_id, period_label, period_start, period_end,
    hours, rate, currency. `amount = hours * rate`. `issue_date` défaut =
    aujourd'hui si None (passé explicitement en test pour le déterminisme).
    """
    settings = _get_settings(db)

    hours = Decimal(str(data.get("hours", "0")))
    rate = Decimal(str(data.get("rate", "0")))
    amount = hours * rate

    number = str(settings.next_invoice_number)
    month = data.get("month") or _month_key(issue_date or date.today())
    # Émission ancrée sur la FIN DU MOIS DE SERVICE (pas aujourd'hui) sauf date
    # explicite. Échéance = émission + délai de paiement du client.
    if issue_date is None:
        issue_date = _period_end(month)

    client = db.get(models.Client, data["client_id"])
    due_date = issue_date + timedelta(days=_term_days(client))
    invoice = models.Invoice(
        number=number,
        client_id=data["client_id"],
        month=month,
        period_label=data.get("period_label", ""),
        period_start=data.get("period_start"),
        period_end=data.get("period_end"),
        hours=hours,
        rate=rate,
        currency=data.get("currency", "USD"),
        amount=amount,
        issue_date=issue_date,
        due_date=due_date,
        status="due",
    )
    db.add(invoice)

    # Incrément du compteur seulement maintenant (création effective).
    settings.next_invoice_number = settings.next_invoice_number + 1

    db.commit()
    db.refresh(invoice)
    logger.info(
        "📤 [Invoices] create: n°%s client=%d montant=%s %s ✅",
        number, invoice.client_id, amount, invoice.currency,
    )
    return invoice


_EN_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _ordinal(day: int) -> str:
    """1 → 1st, 2 → 2nd, 3 → 3rd, 30 → 30th (style factures Word)."""
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def designation(invoice: models.Invoice) -> str:
    """
    Libellé de prestation (style .docx) selon le mode de facturation.

    THM → « … — 152 hours @ 120 USD/h » · TJM → « … — 20 days @ 900 USD/day ».
    Inclut la période si connue (« 1st to the 30th of May 2026 »).
    """
    period = ""
    if invoice.period_start and invoice.period_end:
        start = _ordinal(invoice.period_start.day)
        end = _ordinal(invoice.period_end.day)
        month = _EN_MONTHS[invoice.period_end.month]
        period = f" for period {start} to the {end} of {month} {invoice.period_end.year}"
    if invoice.rate_unit == "hour":
        qty, unit, per = invoice.hours, "hours", "h"
    else:
        qty, unit, per = invoice.days, "days", "day"
    return (
        f"Consultancy fees{period} — {_plain(qty)} {unit} @ {_plain(invoice.rate)} "
        f"{invoice.currency}/{per}"
    )


def _plain(value: Decimal) -> str:
    """Formate un Decimal sans zéros décimaux inutiles (152.00 → 152, 16.50 → 16.5)."""
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def generate_invoice(
    db: Session, invoice_id: int, issue_date: Optional[date] = None
) -> models.Invoice:
    """
    Génère une facture prévisionnelle : `forecast` → `due`.

    Attribue le numéro réel (compteur Settings, incrémenté), pose `issue_date`
    (défaut aujourd'hui), `due_date = issue_date + payment_terms_days` du client,
    la période (mois de `invoice.month`) et passe le statut à `due`.
    Lève 404 si absente, 409 si déjà générée (statut ≠ forecast).
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if invoice.status != "forecast":
        raise HTTPException(status_code=409, detail="Facture déjà générée")

    settings = _get_settings(db)
    client = db.get(models.Client, invoice.client_id)
    year, month = int(invoice.month[:4]), int(invoice.month[5:7])
    # Émission = fin du mois de SERVICE (pas aujourd'hui) sauf date explicite ;
    # échéance = fin de mois + délai de paiement du client.
    if issue_date is None:
        issue_date = _period_end(invoice.month)

    invoice.number = str(settings.next_invoice_number)
    invoice.issue_date = issue_date
    invoice.due_date = issue_date + timedelta(days=_term_days(client))
    invoice.period_start = date(year, month, 1)
    invoice.period_end = date(year, month, calendar.monthrange(year, month)[1])
    invoice.period_label = f"{_EN_MONTHS[month]} {year}"
    invoice.status = "due"

    settings.next_invoice_number = settings.next_invoice_number + 1
    db.commit()
    db.refresh(invoice)
    logger.info(
        "📤 [Invoices] generate: n°%s client=%d (forecast→due) ✅",
        invoice.number, invoice.client_id,
    )
    return invoice


def render_html(db: Session, invoice: models.Invoice) -> str:
    """
    Rend le HTML de la facture (Jinja2) avec infos société + client.

    Retourne une chaîne HTML. Aucune dépendance système (testable seul).
    """
    settings = _get_settings(db)
    client = db.get(models.Client, invoice.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client de la facture introuvable")

    template = _jinja_env.get_template("invoice.html")
    html = template.render(
        company=settings,
        client=client,
        invoice=invoice,
        designation=designation(invoice),
    )
    logger.info("📤 [Invoices] render_html: n°%s ✅", invoice.number)
    return html


def generate_pdf(db: Session, invoice: models.Invoice) -> str:
    """
    Génère le PDF de la facture via WeasyPrint (import paresseux).

    Sauvegarde dans data/invoices/<number>.pdf, pose `invoice.pdf_path`, commit,
    retourne le chemin. Lève HTTPException(503) si WeasyPrint indisponible.
    """
    # WeasyPrint en SOUS-PROCESSUS : sur macOS, dyld lit DYLD_FALLBACK_LIBRARY_PATH
    # au lancement du process — impossible à injecter dans un serveur déjà démarré.
    # Le sous-processus reçoit le chemin des libs Homebrew (pango/cairo/gobject),
    # surchargeable via WEASYPRINT_LIB_PATH (env, pas de chemin métier en dur).
    import os
    import subprocess
    import sys
    import tempfile

    html = render_html(db, invoice)

    _INVOICES_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _INVOICES_DIR / f"{invoice.number}.pdf"

    lib_path = os.environ.get("WEASYPRINT_LIB_PATH")
    if not lib_path:
        for candidate in ("/opt/homebrew/lib", "/usr/local/lib"):
            if Path(candidate).exists():
                lib_path = candidate
                break
    env = {**os.environ}
    if lib_path:
        env["DYLD_FALLBACK_LIBRARY_PATH"] = lib_path

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
        tmp.write(html)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "weasyprint", tmp_path, str(pdf_path)],
            env=env, capture_output=True, text=True, timeout=60,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if result.returncode != 0 or not pdf_path.exists():
        logger.error("❌ [Invoices] generate_pdf: %s", result.stderr[-400:])
        raise HTTPException(
            status_code=503,
            detail="PDF engine indisponible (installer pango/cairo : brew install pango glib)",
        )

    invoice.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(invoice)
    logger.info("📤 [Invoices] generate_pdf: n°%s → %s ✅", invoice.number, pdf_path)
    return str(pdf_path)


_CENTS = Decimal("0.01")


def _q(amount: Decimal) -> Decimal:
    """Arrondit un Decimal à 2 décimales (centimes)."""
    return Decimal(amount).quantize(_CENTS)


def reprice_theoretical_eur(db: Session) -> int:
    """
    Recale le montant EUR **prévisionnel** (théorique) de toutes les factures sur
    le taux FX courant des Réglages.

    Le « € (prév.) » est une projection au taux courant, PAS un instantané figé :
    seul le réalisé (`amount_eur_received`, issu des conversions Revolut) est figé.
    À rejouer dès que les taux changent (hook sur PUT /api/fx-rates). Met aussi à
    jour la variance des factures payées (réel − prévision recalée).
    Retourne le nombre de factures modifiées.
    """
    rates = fx.load_rates(db)
    changed = 0
    for inv in db.query(models.Invoice).all():
        new_fc = _q(fx.to_eur(inv.amount, inv.currency, rates))
        rate = fx.rate_for(rates, inv.currency)
        touched = False
        if inv.amount_eur_forecast != new_fc:
            inv.amount_eur_forecast = new_fc
            touched = True
        if inv.fx_rate_forecast != rate:
            inv.fx_rate_forecast = rate
            touched = True
        if inv.status == "paid" and inv.amount_eur_received is not None:
            new_var = _q(Decimal(inv.amount_eur_received) - new_fc)
            if inv.variance_eur != new_var:
                inv.variance_eur = new_var
                touched = True
        if touched:
            changed += 1
    db.commit()
    logger.info("📤 [Invoices] reprice_theoretical_eur: %d facture(s) recalées ✅", changed)
    return changed


def _month_key(d: date) -> str:
    """Clé mois 'YYYY-MM'."""
    return f"{d.year:04d}-{d.month:02d}"


def _last_six_months(today: date) -> list[str]:
    """Les 6 derniers mois (clés 'YYYY-MM') jusqu'au mois courant inclus, chronologiques."""
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(6):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(keys))


def _derive_status(invoice: models.Invoice, today: date) -> str:
    """forecast / paid / overdue (due_date < today) / due (sinon)."""
    if invoice.status == "forecast":
        return "forecast"
    if invoice.status == "paid":
        return "paid"
    if invoice.due_date is not None and invoice.due_date < today:
        return "overdue"
    return "due"


def timeline(db: Session, today: Optional[date] = None) -> dict:
    """
    Timeline de facturation : montants mensuels (payé / dû / en retard) empilés
    + liste des factures ouvertes (non payées).

    - Statut dérivé par facture : paid, overdue (due_date < today), due (sinon).
    - `months` : 6 derniers mois jusqu'au mois courant inclus (par issue_date),
      chronologiques ; montants natifs convertis en EUR (taux théoriques FX).
    - `outstanding_eur` : somme EUR des factures non payées.
    - `open` : factures non payées triées par due_date, avec statut due|overdue.
    Tous les montants en `Decimal` à 2 décimales.
    """
    if today is None:
        today = date.today()

    rates = fx.load_rates(db)
    invoices = db.query(models.Invoice).all()

    month_keys = _last_six_months(today)
    buckets: dict[str, dict[str, Decimal]] = {
        key: {
            "paid_eur": Decimal("0"),
            "due_eur": Decimal("0"),
            "overdue_eur": Decimal("0"),
        }
        for key in month_keys
    }

    outstanding = Decimal("0")
    open_rows: list[dict] = []

    for inv in invoices:
        status = _derive_status(inv, today)
        # Les factures prévisionnelles ne sont pas encore dues : hors timeline/outstanding.
        if status == "forecast":
            continue
        amount_eur = fx.to_eur(inv.amount, inv.currency, rates)

        if inv.issue_date is not None:
            key = _month_key(inv.issue_date)
            if key in buckets:
                buckets[key][f"{status}_eur"] += amount_eur

        if status != "paid":
            outstanding += amount_eur
            open_rows.append(
                {
                    "number": inv.number,
                    "client_code": inv.client.code if inv.client is not None else None,
                    "currency": inv.currency,
                    "amount": _q(inv.amount),
                    "amount_eur": _q(amount_eur),
                    "status": status,
                    "_due_date": inv.due_date,
                }
            )

    # Tri par due_date (les factures sans due_date en dernier).
    open_rows.sort(key=lambda r: (r["_due_date"] is None, r["_due_date"] or date.max))
    for row in open_rows:
        row.pop("_due_date")

    months = [
        {
            "month": key,
            "paid_eur": _q(buckets[key]["paid_eur"]),
            "due_eur": _q(buckets[key]["due_eur"]),
            "overdue_eur": _q(buckets[key]["overdue_eur"]),
        }
        for key in month_keys
    ]

    logger.info(
        "📤 [Invoices] timeline: %d mois, outstanding=%s, open=%d ✅",
        len(months), _q(outstanding), len(open_rows),
    )
    return {
        "months": months,
        "outstanding_eur": _q(outstanding),
        "open": open_rows,
        "open_count": len(open_rows),
    }


def _amount_matches(tx: models.Transaction, invoice: models.Invoice) -> bool:
    """
    Vrai si le montant de la transaction matche la facture (à tolérance près).

    Même devise → comparaison des montants natifs (rapprochement FX exact).
    Devises différentes → repli sur l'EUR (théorique côté facture).
    """
    if tx.currency and invoice.currency and tx.currency == invoice.currency:
        tx_amount, target = tx.amount, invoice.amount
    else:
        tx_amount = tx.amount_eur if tx.amount_eur is not None else tx.amount
        target = invoice.amount_eur_forecast or invoice.amount
    if tx_amount is None or target is None:
        return False
    return abs(abs(tx_amount) - abs(target)) <= _RECONCILE_TOLERANCE


def _apply_payment(invoice: models.Invoice, tx: models.Transaction) -> None:
    """
    Rattache une transaction encaissée à une facture (passe la facture `paid`).

    Fige le réel : date, montant natif reçu, taux FX réel, montant EUR reçu, et la
    variance EUR = réel encaissé − prévisionnel (0 si pas de prévision).
    """
    invoice.paid_transaction_id = tx.id
    invoice.status = "paid"
    invoice.paid_date = tx.booked_date
    invoice.amount_received = tx.amount
    invoice.fx_rate = tx.fx_rate
    # EUR reçu : le réel figé sur la transaction (`amount_eur`, via fx_realized) prime.
    # Sinon, une transaction déjà en EUR vaut son montant ; une transaction en devise
    # sans FX réel calculé reste `None` (JAMAIS le natif interprété comme des euros —
    # `allocate` la remplira). La variance suit : None tant que l'EUR reçu est inconnu.
    if tx.amount_eur is not None:
        eur_received = Decimal(tx.amount_eur)
    elif (tx.currency or "EUR").upper() == "EUR":
        eur_received = Decimal(tx.amount or 0)
    else:
        eur_received = None
    invoice.amount_eur_received = eur_received
    forecast_eur = invoice.amount_eur_forecast or Decimal("0")
    invoice.variance_eur = (
        _q(eur_received) - _q(forecast_eur) if eur_received is not None else None
    )
    tx.invoice_id = invoice.id


def reconcile_candidates(db: Session, invoice_id: int) -> list[models.Transaction]:
    """
    Transactions candidates au rapprochement manuel d'une facture.

    Revenus (kind='revenue' ou montant positif) non encore rattachés à une
    facture, triés par proximité de montant puis date décroissante.
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    txs = (
        db.execute(
            select(models.Transaction).where(models.Transaction.invoice_id.is_(None))
        )
        .scalars()
        .all()
    )
    revenue = [
        t for t in txs if t.kind == "revenue" or (t.amount is not None and t.amount > 0)
    ]

    def _key(t: models.Transaction):
        tx_amt = t.amount if t.currency == invoice.currency else (t.amount_eur or t.amount)
        target = invoice.amount if t.currency == invoice.currency else (
            invoice.amount_eur_forecast or invoice.amount
        )
        gap = abs(abs(tx_amt or Decimal("0")) - abs(target or Decimal("0")))
        return (gap, -(t.booked_date.toordinal() if t.booked_date else 0))

    revenue.sort(key=_key)
    return revenue


def manual_reconcile(
    db: Session, invoice_id: int, transaction_id: int
) -> models.Invoice:
    """
    Rapproche manuellement une facture avec une transaction choisie.

    404 si l'un est absent ; 409 si la facture est prévisionnelle (à générer
    d'abord) ou si la transaction est déjà rattachée à une autre facture.
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    tx = db.get(models.Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    if invoice.status == "forecast":
        raise HTTPException(status_code=409, detail="Générer la facture avant rapprochement")
    if invoice.status == "paid":
        # Re-rapprocher directement laisserait l'ancienne transaction rattachée
        # (fantôme, exclue à tort du P&L) : passer par unreconcile d'abord.
        raise HTTPException(
            status_code=409,
            detail="Facture déjà payée — annuler le rapprochement avant d'en lier un autre",
        )
    if tx.invoice_id is not None and tx.invoice_id != invoice.id:
        raise HTTPException(status_code=409, detail="Transaction déjà rattachée")

    _apply_payment(invoice, tx)
    db.commit()
    # Recalcule le FX réel (comme le fait la synchro bancaire) : rattache la nouvelle
    # transaction aux conversions et fige le vrai EUR reçu + variance sur la facture.
    # Indispensable ici, sinon l'EUR reçu resterait figé/inconnu jusqu'au prochain sync.
    from backend.services.fx_realized import allocate as allocate_fx

    allocate_fx(db)
    db.refresh(invoice)
    logger.info("✅ [Invoices] manual_reconcile: n°%s ↔ tx#%d ✅", invoice.number, tx.id)
    return invoice


def unreconcile(db: Session, invoice_id: int) -> models.Invoice:
    """
    Annule le rapprochement d'une facture payée : repasse `due`, libère la
    transaction et efface les champs de paiement/variance. 404 si absente,
    409 si la facture n'est pas payée (rien à annuler — et sur une prévision
    l'opération poserait `due` sans numéro réel ni dates).
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if invoice.status != "paid":
        raise HTTPException(status_code=409, detail="Facture non payée — rien à annuler")

    if invoice.paid_transaction_id is not None:
        tx = db.get(models.Transaction, invoice.paid_transaction_id)
        if tx is not None:
            tx.invoice_id = None
    invoice.status = "due"
    invoice.paid_transaction_id = None
    invoice.paid_date = None
    invoice.amount_received = None
    invoice.fx_rate = None
    invoice.amount_eur_received = None
    invoice.variance_eur = None
    db.commit()
    db.refresh(invoice)
    logger.info("↩️ [Invoices] unreconcile: n°%s → due ✅", invoice.number)
    return invoice


def delete_invoice(db: Session, invoice_id: int) -> None:
    """
    Supprime une facture. Si elle est rapprochée, libère d'abord la transaction
    liée (elle redevient candidate au rapprochement), puis efface le PDF sur
    disque s'il existe. 404 si absente.
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    if invoice.paid_transaction_id is not None:
        tx = db.get(models.Transaction, invoice.paid_transaction_id)
        if tx is not None:
            tx.invoice_id = None

    if invoice.pdf_path:
        pdf = Path(invoice.pdf_path)
        try:
            if pdf.exists():
                pdf.unlink()
        except OSError as exc:
            logger.warning("⚠️ [Invoices] delete: PDF non effacé (%s): %s", pdf, exc)

    number = invoice.number
    # Reprise de numérotation : si on supprime la facture au dernier numéro émis,
    # on rend ce numéro (compteur -1) pour ne pas laisser de trou. Ne s'applique
    # qu'aux factures réellement émises (numéro entier) — pas aux prévisionnelles
    # (numéro provisoire « F-… » non numérique).
    if invoice.status != "forecast" and number and number.isdigit():
        settings = _get_settings(db)
        if int(number) == settings.next_invoice_number - 1:
            settings.next_invoice_number = int(number)
            logger.info("🔢 [Invoices] delete: compteur rendu → %s", number)

    db.delete(invoice)
    db.commit()
    logger.info("🗑️ [Invoices] delete: n°%s ✅", number)


def rollback_to_forecast(db: Session, invoice_id: int) -> models.Invoice:
    """
    Repasse une facture ÉMISE (`due`) en prévision (`forecast`) — action dédiée,
    seule voie autorisée pour « dé-générer » (le PATCH de statut est verrouillé).

    Garde-fous (numérotation légale continue) :
    - 404 si absente ; 409 si `forecast` (rien à faire) ou `paid` (annuler le
      rapprochement d'abord) ;
    - 409 si ce n'est PAS le dernier numéro émis — un rollback au milieu de la
      séquence créerait un trou définitif. Roll-backer dans l'ordre inverse.

    Effets : numéro rendu au compteur, numéro provisoire « F-{client}-{mois} »
    reposé, dates d'émission/échéance et période effacées, PDF supprimé.
    """
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if invoice.status == "forecast":
        raise HTTPException(status_code=409, detail="Déjà une prévision")
    if invoice.status == "paid":
        raise HTTPException(
            status_code=409, detail="Facture payée — annuler le rapprochement d'abord"
        )

    settings = _get_settings(db)
    number = invoice.number or ""
    if not number.isdigit() or int(number) != settings.next_invoice_number - 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Seule la dernière facture émise (n°{settings.next_invoice_number - 1}) "
                "peut repasser en prévision — sinon la numérotation aurait un trou"
            ),
        )

    provisional = f"F-{invoice.client_id}-{invoice.month}"
    clash = (
        db.query(models.Invoice)
        .filter(models.Invoice.number == provisional, models.Invoice.id != invoice.id)
        .first()
    )
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail="Une prévision existe déjà pour ce client et ce mois",
        )

    if invoice.pdf_path:
        pdf = Path(invoice.pdf_path)
        try:
            if pdf.exists():
                pdf.unlink()
        except OSError as exc:
            logger.warning("⚠️ [Invoices] rollback: PDF non effacé (%s): %s", pdf, exc)

    settings.next_invoice_number = int(number)  # numéro rendu
    invoice.number = provisional
    invoice.status = "forecast"
    invoice.issue_date = None
    invoice.due_date = None
    invoice.period_label = ""
    invoice.period_start = None
    invoice.period_end = None
    invoice.pdf_path = ""
    db.commit()
    db.refresh(invoice)
    logger.info("↩️ [Invoices] rollback: n°%s → prévision (%s) ✅", number, provisional)
    return invoice


def reconcile_payments(db: Session) -> int:
    """
    Rapproche les factures non payées avec des transactions de revenu.

    Pour chaque facture 'draft'/'sent' non déjà réglée, cherche une transaction
    de revenu (kind='revenue' ou montant positif) dont le montant matche (à
    tolérance) et dont la contrepartie/description contient le
    `counterparty_match` du client, non déjà rattachée à une autre facture.
    Relie (paid_transaction_id, status='paid', transaction.invoice_id).
    Retourne le nombre de factures rapprochées.
    """
    invoices = (
        db.execute(
            select(models.Invoice)
            .where(models.Invoice.status == "due")
            .where(models.Invoice.paid_transaction_id.is_(None))
            .order_by(models.Invoice.id.asc())
        )
        .scalars()
        .all()
    )

    reconciled = 0
    for invoice in invoices:
        client = db.get(models.Client, invoice.client_id)
        match_token = (client.counterparty_match or "").strip().lower() if client else ""

        candidates = (
            db.execute(
                select(models.Transaction)
                .where(models.Transaction.invoice_id.is_(None))
                .order_by(models.Transaction.id.asc())
            )
            .scalars()
            .all()
        )

        for tx in candidates:
            is_revenue = tx.kind == "revenue" or (tx.amount is not None and tx.amount > 0)
            if not is_revenue:
                continue
            if not _amount_matches(tx, invoice):
                continue
            if match_token:
                haystack = f"{tx.counterparty or ''} {tx.description or ''}".lower()
                if match_token not in haystack:
                    continue

            _apply_payment(invoice, tx)
            reconciled += 1
            logger.info(
                "✅ [Invoices] reconcile: facture n°%s ↔ tx#%d (%s)",
                invoice.number, tx.id, invoice.amount,
            )
            break

    db.commit()
    logger.info("📤 [Invoices] reconcile_payments: %d facture(s) rapprochée(s) ✅", reconciled)
    return reconciled
