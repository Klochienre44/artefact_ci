"""
Endpoint POST /processDate -- Traitement et normalisation des colonnes de dates.
"""

import time
import logging

from fastapi import APIRouter

from app.utils.schemas import ProcessDateRequest, ProcessDateResponse
from app.services.minio_service import read_file_from_minio, write_file_to_minio
from app.services.date_service import normalize_date_columns
from app.core.telemetry import get_tracer

logger = logging.getLogger("arteci.router.date")
tracer = get_tracer()

router = APIRouter()


@router.post(
    "/processDate",
    response_model=ProcessDateResponse,
    summary="Normaliser les colonnes de dates d'un fichier",
    description="""
Endpoint principal d'ARTECI.

Lit le fichier depuis MinIO, normalise les colonnes de dates specifiees
(DMY, MDY ou AUTO), ecrase le fichier dans MinIO avec les donnees
traitees, puis retourne un apercu des 100 premieres lignes.

**Format de sortie** : `JJ-MM-AAAA HH:mm:ss`

**Regle metier** : une cellule mal formatee est retournee telle quelle
sans bloquer le traitement de la colonne ou du fichier.

**Exemple de colonnes** : DATE_CREATION, DATE_DESACTIVATION, DATE_DERNIERE_CONNECTION_1
    """,
)
async def process_date(body: ProcessDateRequest) -> ProcessDateResponse:
    """Normalise les colonnes de dates du fichier stocke dans MinIO."""

    with tracer.start_as_current_span("endpoint.processDate") as span:
        span.set_attribute("request.bucket", body.bucket)
        span.set_attribute("request.file", body.file)
        span.set_attribute("request.date_columns", str(body.date_columns))
        span.set_attribute("request.date_formats", str(body.date_formats))

        start = time.perf_counter()
        logger.info("Debut traitement bucket=%s file=%s colonnes=%s",
                    body.bucket, body.file, body.date_columns)

        raw_content = read_file_from_minio(body.bucket, body.file)

        processed_bytes, preview, content_type = normalize_date_columns(
            content=raw_content,
            file_path=body.file,
            date_columns=body.date_columns,
            date_formats=body.date_formats,
        )

        write_file_to_minio(body.bucket, body.file, processed_bytes, content_type)

        elapsed = round(time.perf_counter() - start, 3)
        logger.info("Traitement termine bucket=%s file=%s elapsed=%.3fs",
                    body.bucket, body.file, elapsed)

        span.set_attribute("response.elapsed_s", elapsed)

        return ProcessDateResponse(
            success=True,
            file=body.file,
            bucket=body.bucket,
            rows_processed=len(preview),
            columns_normalized=body.date_columns,
            preview=preview,
            elapsed_seconds=elapsed,
        )
