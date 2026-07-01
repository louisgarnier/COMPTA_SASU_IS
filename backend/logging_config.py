"""
Fondation logging LGC (Step 4 méthodo).

- Trois fichiers datés : logs/backend_YYYY-MM-DD.log, api_*.log, frontend_*.log.
- Format : `[ModuleName] verb: detail` avec niveau + timestamp.
- Masquage systématique des IBAN et emails (jamais de PII/secret en clair).
- Emojis conventionnels : 📥 in · 📤 out · ✅ ok · ❌ err · ⚠️ warn · 🗄️ db · 🚀 startup.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from backend.config import settings

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+")


def _mask(text: str) -> str:
    """Masque IBAN, emails et secrets évidents dans un message de log."""
    text = _IBAN_RE.sub(lambda m: m.group(0)[:4] + "****" + m.group(0)[-2:], text)
    text = _EMAIL_RE.sub(lambda m: m.group(0).split("@")[0][:2] + "***@***", text)
    text = _SECRET_RE.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***", text)
    return text


class _MaskingFilter(logging.Filter):
    """Applique le masquage PII sur chaque enregistrement."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _mask(record.msg)
        return True


_FORMAT = "%(asctime)s %(levelname)s %(message)s"
_configured: set[str] = set()


def get_logger(name: str, channel: str = "backend") -> logging.Logger:
    """
    Retourne un logger écrivant dans logs/<channel>_<date>.log + console.

    channel ∈ {'backend', 'api', 'frontend'}.
    """
    logger = logging.getLogger(f"lgc.{channel}.{name}")
    if logger.name in _configured:
        return logger

    logger.setLevel(settings.log_level)
    logger.propagate = False

    log_file = LOG_DIR / f"{channel}_{date.today().isoformat()}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    file_handler.addFilter(_MaskingFilter())

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_FORMAT))
    stream_handler.addFilter(_MaskingFilter())

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    _configured.add(logger.name)
    return logger
