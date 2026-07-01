"""
LGC — API FastAPI (application principale).

Démarrage : crée les tables SQLite, seed les catégories/règles système,
monte tous les routers métier. CORS pour le front Next.js local.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.base import SessionLocal, init_db
from backend.logging_config import get_logger
from backend.services.categorize import seed_default_categories_and_rules

from backend.api.routes import balance_docs as balance_docs_routes
from backend.api.routes import banking as banking_routes
from backend.api.routes import categories as categories_routes
from backend.api.routes import clients as clients_routes
from backend.api.routes import forecast as forecast_routes
from backend.api.routes import investments as investments_routes
from backend.api.routes import invoices as invoices_routes
from backend.api.routes import settings as settings_routes
from backend.api.routes import transactions as transactions_routes
from backend.api.routes import treasury as treasury_routes

log = get_logger("main", channel="backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup : tables + seed système. Shutdown : rien de spécial."""
    log.info("🚀 [Main] startup: init DB + seed catégories")
    init_db()
    db = SessionLocal()
    try:
        seed_default_categories_and_rules(db)
        db.commit()
    finally:
        db.close()
    log.info("✅ [Main] startup terminé")
    yield


app = FastAPI(
    title="LGC API",
    description="LGC — suivi cashflow SASU (API locale)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers métier
app.include_router(settings_routes.router)
app.include_router(clients_routes.router)
app.include_router(investments_routes.router)
app.include_router(transactions_routes.router)
app.include_router(categories_routes.router)
app.include_router(categories_routes.rules_router)
app.include_router(treasury_routes.router)
app.include_router(forecast_routes.router)
app.include_router(invoices_routes.router)
app.include_router(banking_routes.router)
app.include_router(balance_docs_routes.router)


@app.get("/")
async def root():
    """Racine — identifie l'API."""
    return {"message": "LGC API", "status": "ok"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}
