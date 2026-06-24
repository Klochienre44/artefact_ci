"""
Endpoint GET /columns -- Liste des colonnes d'un fichier stocke dans MinIO.
"""

import logging
from fastapi import APIRouter, Query

from app.utils.schemas import ColumnsResponse
from app.services.minio_service import get_file_columns_from_minio
from app.core.telemetry import get_tracer

logger = logging.getLogger("arteci.router.columns")
tracer = get_tracer()

router = APIRouter()


@router.get(
    "/columns",
    response_model=ColumnsResponse,
    summary="Lister les colonnes d'un fichier MinIO",
    description="""
Retourne la liste des noms de colonnes d'un fichier CSV ou Excel
stocke dans un bucket MinIO.

Optimise : seule la premiere ligne est chargee pour extraire les en-tetes.
    """,
)
async def get_columns(
    bucket: str = Query(..., description="Nom du bucket MinIO.", examples=["raw"]),
    file: str = Query(
        ...,
        description="Chemin complet du fichier dans le bucket.",
        examples=["uploads/lst_of_users_anon_1.csv"],
    ),
) -> ColumnsResponse:
    """Retourne la liste des colonnes d'un fichier MinIO."""

    with tracer.start_as_current_span("endpoint.columns") as span:
        span.set_attribute("request.bucket", bucket)
        span.set_attribute("request.file", file)

        logger.info("Recuperation colonnes bucket=%s file=%s", bucket, file)
        columns = get_file_columns_from_minio(bucket, file)

        span.set_attribute("response.columns_count", len(columns))

        return ColumnsResponse(
            file=file,
            bucket=bucket,
            columns=columns,
            count=len(columns),
        )
