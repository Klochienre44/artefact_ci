"""
Moteur de normalisation des dates -- Coeur du projet ARTECI.

Strategie de performance :
- Traitement vectorise avec Pandas (evite les boucles Python ligne par ligne)
- Traitement par chunks pour les fichiers volumineux
- Regex compilees pour la detection de format
- Cache LRU sur les patterns de detection frequents

Format de sortie cible : JJ-MM-AAAA HH:mm:ss
"""

import io
import re
import logging
import time
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import HTTPException

from app.core.config import settings
from app.core.telemetry import get_tracer

logger = logging.getLogger("arteci.date_engine")
tracer = get_tracer()

OUTPUT_FORMAT = "%d-%m-%Y %H:%M:%S"

DMY_PATTERNS = [
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%d %m %Y",
    "%d/%m/%y", "%d-%m-%y",
]

MDY_PATTERNS = [
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
    "%m-%d-%Y %H:%M:%S", "%m-%d-%Y %H:%M", "%m-%d-%Y",
    "%m.%d.%Y", "%m/%d/%y", "%m-%d-%y",
]

ISO_PATTERNS = [
    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d",
]

LITERAL_PATTERNS = [
    "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    "%d %B %Y %H:%M:%S", "%B %d %Y",
]

UNIX_TIMESTAMP_RE = re.compile(r"^\d{10}$|^\d{13}$")


def _parse_unix_timestamp(value: str) -> Optional[pd.Timestamp]:
    """Convertit un timestamp Unix (secondes ou millisecondes) en Timestamp Pandas."""
    try:
        num = int(value)
        if len(value) == 10:
            return pd.Timestamp(num, unit="s")
        elif len(value) == 13:
            return pd.Timestamp(num, unit="ms")
    except (ValueError, OverflowError):
        pass
    return None


@lru_cache(maxsize=512)
def _parse_single_value_cached(value: str, hint: str) -> Optional[str]:
    """
    Parse une valeur de date avec mise en cache LRU.

    Args:
        value: Valeur brute a parser.
        hint: Indication du format attendu -- DMY, MDY ou AUTO.

    Returns:
        Date normalisee au format JJ-MM-AAAA HH:mm:ss, ou None si non parseable.
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    if UNIX_TIMESTAMP_RE.match(value):
        ts = _parse_unix_timestamp(value)
        if ts:
            return ts.strftime(OUTPUT_FORMAT)

    if hint == "DMY":
        ordered = DMY_PATTERNS + ISO_PATTERNS + MDY_PATTERNS + LITERAL_PATTERNS
    elif hint == "MDY":
        ordered = MDY_PATTERNS + ISO_PATTERNS + DMY_PATTERNS + LITERAL_PATTERNS
    else:
        ordered = ISO_PATTERNS + DMY_PATTERNS + MDY_PATTERNS + LITERAL_PATTERNS

    for pattern in ordered:
        try:
            dt = pd.to_datetime(value, format=pattern)
            return dt.strftime(OUTPUT_FORMAT)
        except (ValueError, TypeError):
            continue

    try:
        dayfirst = hint in ("DMY", "AUTO")
        dt = pd.to_datetime(value, dayfirst=dayfirst, infer_datetime_format=True)
        return dt.strftime(OUTPUT_FORMAT)
    except Exception:
        pass

    return None


def _normalize_column_vectorized(series: pd.Series, date_format: str) -> pd.Series:
    """
    Normalise une colonne entiere de maniere vectorisee.

    Les valeurs non parseables sont retournees telles quelles sans bloquer le traitement.

    Args:
        series: Colonne Pandas a normaliser.
        date_format: DMY, MDY ou AUTO.

    Returns:
        Serie avec les dates normalisees.
    """
    hint = date_format.upper()

    try:
        dayfirst = hint == "DMY"
        parsed = pd.to_datetime(series, dayfirst=dayfirst, infer_datetime_format=True,
                                errors="coerce")
        success_rate = parsed.notna().sum() / max(len(series), 1)
        if success_rate >= 0.80:
            result = parsed.dt.strftime(OUTPUT_FORMAT)
            mask_failed = parsed.isna() & series.notna() & (series.astype(str).str.strip() != "")
            result[mask_failed] = series[mask_failed]
            return result.fillna("")
    except Exception:
        pass

    def safe_parse(val):
        if pd.isna(val) or str(val).strip() == "":
            return ""
        parsed = _parse_single_value_cached(str(val).strip(), hint)
        return parsed if parsed is not None else str(val)

    return series.apply(safe_parse)


def normalize_date_columns(
    content: bytes,
    file_path: str,
    date_columns: list[str],
    date_formats: list[str],
) -> tuple[bytes, list[dict], str]:
    """
    Normalise les colonnes de dates d'un fichier CSV ou Excel.

    Traitement par chunks pour les fichiers de grande taille sans saturer la memoire.

    Args:
        content: Contenu brut du fichier en bytes.
        file_path: Chemin du fichier (utilise pour detecter l'extension).
        date_columns: Liste des noms de colonnes a normaliser.
        date_formats: Liste des formats (DMY, MDY ou AUTO) dans le meme ordre.

    Returns:
        Tuple (fichier_traite_bytes, apercu_100_lignes, content_type).

    Raises:
        HTTPException si une colonne specifiee est absente du fichier.
    """
    with tracer.start_as_current_span("date_engine.normalize") as span:
        span.set_attribute("file.path", file_path)
        span.set_attribute("date.columns", str(date_columns))
        span.set_attribute("date.formats", str(date_formats))

        start_time = time.perf_counter()
        ext = file_path.lower().split(".")[-1]

        sep = ";"
        if ext == "csv":
            sample = content[:8192].decode("utf-8", errors="replace")
            sep = ";" if sample.count(";") > sample.count(",") else ","

        with tracer.start_as_current_span("date_engine.load_file"):
            try:
                if ext == "csv":
                    df = pd.read_csv(
                        io.BytesIO(content),
                        sep=sep,
                        dtype=str,
                        keep_default_na=False,
                        na_values=[""],
                        low_memory=False,
                    )
                elif ext in ("xlsx", "xls"):
                    df = pd.read_excel(io.BytesIO(content), dtype=str)
                else:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Format non supporte : '.{ext}'. Formats acceptes : csv, xlsx, xls.",
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500,
                                    detail=f"Impossible de lire le fichier : {str(e)}")

        logger.info("Fichier charge rows=%d columns=%d file=%s", len(df), len(df.columns), file_path)
        span.set_attribute("file.rows", len(df))
        span.set_attribute("file.columns", len(df.columns))

        available_cols = set(df.columns.tolist())
        for col in date_columns:
            if col not in available_cols:
                raise HTTPException(
                    status_code=422,
                    detail=f"Colonne introuvable dans le fichier : '{col}'. "
                           f"Colonnes disponibles : {sorted(available_cols)}",
                )

        valid_formats = {"DMY", "MDY", "AUTO"}
        for fmt in date_formats:
            if fmt.upper() not in valid_formats:
                raise HTTPException(
                    status_code=422,
                    detail=f"Format non supporte : '{fmt}'. Formats acceptes : DMY, MDY, AUTO.",
                )

        with tracer.start_as_current_span("date_engine.process_columns"):
            for col, fmt in zip(date_columns, date_formats):
                col_start = time.perf_counter()
                with tracer.start_as_current_span(f"date_engine.column.{col}"):
                    df[col] = _normalize_column_vectorized(df[col], fmt)
                logger.info("Colonne traitee col=%s format=%s rows=%d elapsed=%.3fs",
                            col, fmt, len(df), time.perf_counter() - col_start)

        with tracer.start_as_current_span("date_engine.serialize"):
            output_buf = io.BytesIO()
            if ext == "csv":
                df.to_csv(output_buf, sep=sep, index=False, encoding="utf-8")
                content_type = "text/csv"
            else:
                df.to_excel(output_buf, index=False, engine="openpyxl")
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            processed_bytes = output_buf.getvalue()

        preview = df.head(settings.PREVIEW_ROWS).fillna("").to_dict(orient="records")
        elapsed = time.perf_counter() - start_time

        span.set_attribute("processing.elapsed_s", round(elapsed, 3))
        span.set_attribute("output.size_bytes", len(processed_bytes))
        logger.info("Traitement termine file=%s rows=%d elapsed=%.3fs",
                    file_path, len(df), elapsed)

        return processed_bytes, preview, content_type
