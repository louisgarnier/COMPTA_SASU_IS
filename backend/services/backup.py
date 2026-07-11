"""
Sauvegarde automatique de la base SQLite (data/lgc.db).

- Copie cohérente via l'API backup de sqlite3 (sûre même pendant une écriture),
  jamais un simple cp de fichier.
- Destination : data/backups/lgc_YYYYMMDD_HHMMSS_<reason>.db
- Rotation : toutes les sauvegardes du jour sont gardées ; pour chaque jour
  passé seule la PREMIÈRE est conservée (état d'avant la première synchro du
  jour) ; au-delà de RETENTION_DAYS tout est supprimé.
"""

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from backend.db.base import engine
from backend.logging_config import get_logger

logger = get_logger("Backup", "backend")

RETENTION_DAYS = 30
_BACKUP_RE = re.compile(r"lgc_(\d{8})_(\d{6})_[a-z]+\.db")


def _default_db_path() -> Path:
    """Chemin du fichier SQLite réellement utilisé par l'app."""
    return Path(engine.url.database)


def create_backup(
    src: Optional[Path] = None,
    dest_dir: Optional[Path] = None,
    reason: str = "sync",
) -> Path:
    """Sauvegarde la base et applique la rotation. Retourne le fichier créé."""
    src = Path(src) if src else _default_db_path()
    if not src.exists():
        raise FileNotFoundError(f"Base introuvable : {src}")
    dest_dir = Path(dest_dir) if dest_dir else src.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"lgc_{stamp}_{reason}.db"

    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    logger.info("📤 [Backup] create: %s (%d octets) ✅", dest.name, dest.stat().st_size)
    prune_backups(dest_dir)
    return dest


def prune_backups(dest_dir: Path, today: Optional[date] = None) -> None:
    """Rotation : tout aujourd'hui, 1re du jour pour J-1..J-30, rien au-delà."""
    today = today or date.today()
    first_of_day: dict[str, Path] = {}

    for path in sorted(Path(dest_dir).iterdir()):
        m = _BACKUP_RE.fullmatch(path.name)
        if not m:
            continue  # fichier étranger : ne pas toucher
        day_str = m.group(1)
        day = datetime.strptime(day_str, "%Y%m%d").date()
        if day == today:
            continue  # tout le jour courant est gardé
        if (today - day).days > RETENTION_DAYS:
            path.unlink()
            logger.info("📤 [Backup] prune (>%dj): %s", RETENTION_DAYS, path.name)
        elif day_str in first_of_day:
            path.unlink()  # une seule sauvegarde par jour passé (la première)
            logger.info("📤 [Backup] prune (doublon du jour): %s", path.name)
        else:
            first_of_day[day_str] = path
