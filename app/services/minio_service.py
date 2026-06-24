"""
Service d'acces a MinIO -- Lecture et ecriture des fichiers CSV/Excel.
Utilise le streaming pour eviter de saturer la memoire sur les fichiers volumineux.
"""

import io
import logging
from typing import Optional

from minio import Minio
from minio.error import S3Error
from fastapi import HTTPException

from app.core.config import settings
from app.core.telemetry import get_tracer

logger = logging.getLogger("arteci.minio")
tracer = get_tracer()


def get_minio_client() -> Minio:
    """Cree et retourne un client MinIO."""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def read_file_from_minio(bucket: str, file_path: str) -> bytes:
    """
    Lit un fichier depuis MinIO et retourne son contenu brut.

    Args:
        bucket: Nom du bucket MinIO.
        file_path: Chemin complet du fichier dans le bucket.

    Returns:
        Contenu brut du fichier en bytes.

    Raises:
        HTTPException 404 si le fichier ou le bucket est introuvable.
        HTTPException 500 pour les autres erreurs MinIO.
    """
    with tracer.start_as_current_span("minio.read_file") as span:
        span.set_attribute("minio.bucket", bucket)
        span.set_attribute("minio.file", file_path)

        client = get_minio_client()
        try:
            response = client.get_object(bucket, file_path)
            content = response.read()
            span.set_attribute("minio.file_size_bytes", len(content))
            logger.info("Fichier lu depuis MinIO bucket=%s file=%s size=%d",
                        bucket, file_path, len(content))
            return content
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchBucket"):
                logger.warning("Fichier introuvable dans MinIO bucket=%s file=%s error=%s",
                               bucket, file_path, str(e))
                raise HTTPException(
                    status_code=404,
                    detail=f"Fichier introuvable : bucket='{bucket}', fichier='{file_path}'.",
                )
            logger.error("Erreur MinIO lors de la lecture bucket=%s file=%s error=%s",
                         bucket, file_path, str(e))
            raise HTTPException(status_code=500, detail=f"Erreur MinIO : {str(e)}")
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass


def write_file_to_minio(bucket: str, file_path: str, content: bytes,
                         content_type: str = "text/csv") -> None:
    """
    Ecrit un fichier dans MinIO.

    Args:
        bucket: Nom du bucket MinIO.
        file_path: Chemin complet du fichier dans le bucket.
        content: Contenu a ecrire en bytes.
        content_type: Type MIME du fichier.

    Raises:
        HTTPException 500 en cas d'erreur MinIO.
    """
    with tracer.start_as_current_span("minio.write_file") as span:
        span.set_attribute("minio.bucket", bucket)
        span.set_attribute("minio.file", file_path)
        span.set_attribute("minio.file_size_bytes", len(content))

        client = get_minio_client()
        try:
            data_stream = io.BytesIO(content)
            client.put_object(
                bucket_name=bucket,
                object_name=file_path,
                data=data_stream,
                length=len(content),
                content_type=content_type,
            )
            logger.info("Fichier ecrit dans MinIO bucket=%s file=%s size=%d",
                        bucket, file_path, len(content))
        except S3Error as e:
            logger.error("Erreur MinIO lors de l'ecriture bucket=%s file=%s error=%s",
                         bucket, file_path, str(e))
            raise HTTPException(status_code=500,
                                detail=f"Erreur lors de l'ecriture dans MinIO : {str(e)}")


def get_file_columns_from_minio(bucket: str, file_path: str) -> list[str]:
    """
    Lit uniquement les colonnes d'un fichier MinIO sans charger toutes les donnees.

    Args:
        bucket: Nom du bucket MinIO.
        file_path: Chemin complet du fichier dans le bucket.

    Returns:
        Liste des noms de colonnes.

    Raises:
        HTTPException si le fichier est introuvable ou le format non supporte.
    """
    import pandas as pd

    with tracer.start_as_current_span("minio.get_columns") as span:
        span.set_attribute("minio.bucket", bucket)
        span.set_attribute("minio.file", file_path)

        content = read_file_from_minio(bucket, file_path)
        ext = file_path.lower().split(".")[-1]

        try:
            if ext == "csv":
                sample = content[:4096].decode("utf-8", errors="replace")
                sep = ";" if sample.count(";") > sample.count(",") else ","
                df = pd.read_csv(io.BytesIO(content), sep=sep, nrows=0)
            elif ext in ("xlsx", "xls"):
                df = pd.read_excel(io.BytesIO(content), nrows=0)
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Format non supporte : '.{ext}'. Formats acceptes : csv, xlsx, xls.",
                )
            columns = df.columns.tolist()
            span.set_attribute("minio.columns_count", len(columns))
            logger.info("Colonnes extraites bucket=%s file=%s colonnes=%s",
                        bucket, file_path, columns)
            return columns
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Erreur lecture colonnes : %s", str(e))
            raise HTTPException(status_code=500,
                                detail=f"Impossible de lire les colonnes : {str(e)}")
