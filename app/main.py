"""
ARTECI - API de Standardisation des Dates
Artefact Cote d'Ivoire -- Challenge DevOps / Data Platform
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.telemetry import setup_telemetry
from app.routers import date_router, columns_router

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger("arteci")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application."""
    logger.info("Demarrage ARTECI API version %s", settings.APP_VERSION)
    setup_telemetry()
    yield
    logger.info("Arret ARTECI API")


app = FastAPI(
    title="ARTECI - API de Standardisation des Dates",
    description="""
API haute performance pour la normalisation des colonnes de dates.

Supporte les formats DMY (Jour/Mois/Annee) et MDY (Mois/Jour/Annee)
ainsi que leurs variantes et les timestamps.

Sortie standardisee : **JJ-MM-AAAA HH:mm:ss**
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(date_router.router, tags=["Traitement des dates"])
app.include_router(columns_router.router, tags=["Colonnes"])


@app.get("/health", tags=["Sante"])
async def health_check():
    """Verification de l'etat de l'API."""
    return {"status": "ok", "version": settings.APP_VERSION, "service": "arteci-api"}
