"""
LGC — API FastAPI (application principale).

Squelette S1.1 : expose `/` et `/health`, CORS pour le front local.
Aucune dépendance base de données ici (couche DB = S1.2).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
app = FastAPI(
    title="LGC API",
    description="LGC — suivi cashflow SASU (API locale)",
    version="0.1.0",
)

# CORS — autorise le front Next.js local (middleware couche la plus externe)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Racine — identifie l'API."""
    return {"message": "LGC API", "status": "ok"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}
