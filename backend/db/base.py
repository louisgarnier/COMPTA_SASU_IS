"""
Moteur SQLAlchemy + session pour LGC.

- SQLite local (fichier `data/lgc.db`), `PRAGMA foreign_keys=ON` activé sur chaque connexion.
- Montants manipulés en `Decimal` (colonnes `Numeric`), jamais en float.
"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles."""


# Le fichier SQLite vit dans data/ (gitignored). On s'assure que le dossier existe.
_db_url = settings.database_url
if _db_url.startswith("sqlite:///./"):
    rel = _db_url.replace("sqlite:///./", "", 1)
    db_path = Path(__file__).resolve().parents[2] / rel
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db_url = f"sqlite:///{db_path}"

engine = create_engine(
    _db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if _db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Active l'intégrité référentielle SQLite (désactivée par défaut)."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # Non-SQLite : rien à faire.
        pass


def get_db():
    """Dépendance FastAPI : fournit une session, la ferme en fin de requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crée toutes les tables si absentes (dev local ; migrations = Alembic)."""
    # Import pour enregistrer les modèles sur Base.metadata.
    from backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
