"""
Tests ARTECI -- Unitaires et Integration

Couvre :
  - Normalisation des formats DMY, MDY, ISO et timestamps Unix
  - Valeurs manquantes et mal formatees (sans blocage du traitement)
  - Endpoint POST /processDate (avec mock MinIO)
  - Endpoint GET /columns (avec mock MinIO)
  - Schemas Pydantic (validation des requetes)

Lancement : pytest tests/ -v
"""

import io
import pytest
import pandas as pd
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.date_service import (
    _parse_single_value_cached,
    _normalize_column_vectorized,
    normalize_date_columns,
)
from app.utils.schemas import ProcessDateRequest

client = TestClient(app)


class TestParseSingleValue:
    """Tests de la fonction de parsing unitaire d'une date."""

    def test_dmy_slash(self):
        result = _parse_single_value_cached("15/06/2023", "DMY")
        assert result == "15-06-2023 00:00:00"

    def test_mdy_slash(self):
        result = _parse_single_value_cached("06/15/2023", "MDY")
        assert result == "15-06-2023 00:00:00"

    def test_iso_with_time(self):
        result = _parse_single_value_cached("2023-06-15 14:30:00", "AUTO")
        assert result == "15-06-2023 14:30:00"

    def test_iso_with_tz(self):
        result = _parse_single_value_cached("2023-06-15T14:30:00Z", "AUTO")
        assert result == "15-06-2023 14:30:00"

    def test_unix_timestamp_seconds(self):
        result = _parse_single_value_cached("1686835800", "AUTO")
        assert result is not None
        assert result.endswith(":00")

    def test_unix_timestamp_milliseconds(self):
        result = _parse_single_value_cached("1686835800000", "AUTO")
        assert result is not None

    def test_dmy_dash(self):
        result = _parse_single_value_cached("15-06-2023", "DMY")
        assert result == "15-06-2023 00:00:00"

    def test_dmy_with_time(self):
        result = _parse_single_value_cached("15/06/2023 08:45:00", "DMY")
        assert result == "15-06-2023 08:45:00"

    def test_mdy_with_time(self):
        result = _parse_single_value_cached("06/15/2023 14:30:00", "MDY")
        assert result == "15-06-2023 14:30:00"

    def test_invalid_date_returns_none(self):
        result = _parse_single_value_cached("not_a_date", "AUTO")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_single_value_cached("", "AUTO")
        assert result is None

    def test_already_normalized(self):
        result = _parse_single_value_cached("15-06-2023 00:00:00", "AUTO")
        assert result == "15-06-2023 00:00:00"


class TestNormalizeColumn:
    """Tests du traitement vectorise d'une colonne entiere."""

    def test_mdy_column_normalized(self):
        series = pd.Series(["01/15/2023", "06/15/2023", "12/31/2022"])
        result = _normalize_column_vectorized(series, "MDY")
        assert result.iloc[0] == "15-01-2023 00:00:00"
        assert result.iloc[1] == "15-06-2023 00:00:00"
        assert result.iloc[2] == "31-12-2022 00:00:00"

    def test_dmy_column_normalized(self):
        series = pd.Series(["15/01/2023", "15/06/2023", "31/12/2022"])
        result = _normalize_column_vectorized(series, "DMY")
        assert result.iloc[0] == "15-01-2023 00:00:00"
        assert result.iloc[1] == "15-06-2023 00:00:00"
        assert result.iloc[2] == "31-12-2022 00:00:00"

    def test_invalid_values_preserved(self):
        series = pd.Series(["01/15/2023", "INVALIDE", ""])
        result = _normalize_column_vectorized(series, "MDY")
        assert result.iloc[0] == "15-01-2023 00:00:00"
        assert isinstance(result.iloc[1], str)

    def test_null_values_handled(self):
        series = pd.Series(["01/15/2023", None, "06/15/2023"])
        result = _normalize_column_vectorized(series, "MDY")
        assert result.iloc[0] == "15-01-2023 00:00:00"
        assert result.iloc[1] == ""
        assert result.iloc[2] == "15-06-2023 00:00:00"

    def test_mixed_formats_auto(self):
        series = pd.Series(["2023-06-15", "15/06/2023", "06/15/2023 14:00:00"])
        result = _normalize_column_vectorized(series, "AUTO")
        for val in result:
            assert isinstance(val, str)
            assert len(val) > 0


class TestNormalizeDateColumns:
    """Tests du moteur de traitement complet sur CSV en memoire."""

    def _make_csv(self, rows: list[dict]) -> bytes:
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        return buf.getvalue()

    def test_basic_normalization(self):
        content = self._make_csv([
            {"NOM": "Alice", "DATE_CREATION": "01/15/2023"},
            {"NOM": "Bob",   "DATE_CREATION": "06/20/1985"},
        ])
        processed, preview, ct = normalize_date_columns(
            content=content, file_path="test.csv",
            date_columns=["DATE_CREATION"], date_formats=["MDY"],
        )
        assert len(preview) == 2
        assert preview[0]["DATE_CREATION"] == "15-01-2023 00:00:00"
        assert preview[1]["DATE_CREATION"] == "20-06-1985 00:00:00"
        assert "text/csv" in ct

    def test_three_date_columns(self):
        """Valide la normalisation de trois colonnes dont DATE_DERNIERE_CONNECTION_1."""
        content = self._make_csv([
            {
                "NOM": "Alice",
                "DATE_CREATION": "01/15/2023",
                "DATE_DESACTIVATION": "12/31/2099",
                "DATE_DERNIERE_CONNECTION_1": "06/01/2024",
            },
        ])
        processed, preview, ct = normalize_date_columns(
            content=content, file_path="test.csv",
            date_columns=["DATE_CREATION", "DATE_DESACTIVATION", "DATE_DERNIERE_CONNECTION_1"],
            date_formats=["MDY", "MDY", "MDY"],
        )
        assert preview[0]["DATE_CREATION"] == "15-01-2023 00:00:00"
        assert preview[0]["DATE_DESACTIVATION"] == "31-12-2099 00:00:00"
        assert preview[0]["DATE_DERNIERE_CONNECTION_1"] == "01-06-2024 00:00:00"

    def test_missing_column_raises_422(self):
        from fastapi import HTTPException
        content = self._make_csv([{"NOM": "Alice", "DATE": "01/15/2023"}])
        with pytest.raises(HTTPException) as exc_info:
            normalize_date_columns(
                content=content, file_path="test.csv",
                date_columns=["COLONNE_INEXISTANTE"], date_formats=["MDY"],
            )
        assert exc_info.value.status_code == 422

    def test_invalid_format_raises_422(self):
        from fastapi import HTTPException
        content = self._make_csv([{"DATE": "01/15/2023"}])
        with pytest.raises(HTTPException) as exc_info:
            normalize_date_columns(
                content=content, file_path="test.csv",
                date_columns=["DATE"], date_formats=["XYZ"],
            )
        assert exc_info.value.status_code == 422

    def test_output_is_readable_csv(self):
        content = self._make_csv([{"DATE": "01/15/2023"}, {"DATE": "06/20/2023"}])
        processed, _, _ = normalize_date_columns(
            content=content, file_path="test.csv",
            date_columns=["DATE"], date_formats=["MDY"],
        )
        df_result = pd.read_csv(io.BytesIO(processed))
        assert "DATE" in df_result.columns
        assert df_result["DATE"].iloc[0] == "15-01-2023 00:00:00"


def _make_sample_csv() -> bytes:
    df = pd.DataFrame([
        {
            "NOM": "Alice",
            "DATE_CREATION": "01/15/2023 08:00:00",
            "DATE_DESACTIVATION": "12/31/2099",
            "DATE_DERNIERE_CONNECTION_1": "06/01/2024",
        },
        {
            "NOM": "Bob",
            "DATE_CREATION": "06/20/2023 14:30:00",
            "DATE_DESACTIVATION": "",
            "DATE_DERNIERE_CONNECTION_1": "05/15/2024",
        },
    ])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


class TestProcessDateEndpoint:
    """Tests d'integration du endpoint POST /processDate."""

    def test_success_three_columns(self):
        sample_csv = _make_sample_csv()
        with patch("app.routers.date_router.read_file_from_minio", return_value=sample_csv), \
             patch("app.routers.date_router.write_file_to_minio") as mock_write:

            response = client.post("/processDate", json={
                "bucket": "raw",
                "file": "uploads/lst_of_users_anon_1.csv",
                "date_columns": ["DATE_CREATION", "DATE_DESACTIVATION", "DATE_DERNIERE_CONNECTION_1"],
                "date_formats": ["MDY", "MDY", "MDY"],
            })

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "DATE_DERNIERE_CONNECTION_1" in body["columns_normalized"]
        mock_write.assert_called_once()

    def test_missing_column_returns_422(self):
        sample_csv = _make_sample_csv()
        with patch("app.routers.date_router.read_file_from_minio", return_value=sample_csv):
            response = client.post("/processDate", json={
                "bucket": "raw",
                "file": "uploads/test.csv",
                "date_columns": ["COLONNE_ABSENTE"],
                "date_formats": ["MDY"],
            })
        assert response.status_code == 422

    def test_columns_formats_mismatch_returns_422(self):
        response = client.post("/processDate", json={
            "bucket": "raw",
            "file": "test.csv",
            "date_columns": ["COL1", "COL2"],
            "date_formats": ["MDY"],
        })
        assert response.status_code == 422

    def test_minio_not_found_returns_404(self):
        from fastapi import HTTPException
        with patch("app.routers.date_router.read_file_from_minio",
                   side_effect=HTTPException(status_code=404, detail="Fichier introuvable")):
            response = client.post("/processDate", json={
                "bucket": "raw",
                "file": "inexistant.csv",
                "date_columns": ["DATE_CREATION"],
                "date_formats": ["MDY"],
            })
        assert response.status_code == 404


class TestColumnsEndpoint:
    """Tests d'integration du endpoint GET /columns."""

    def test_success(self):
        with patch("app.routers.columns_router.get_file_columns_from_minio",
                   return_value=["NOM", "DATE_CREATION", "DATE_DESACTIVATION",
                                 "DATE_DERNIERE_CONNECTION_1"]):
            response = client.get("/columns", params={
                "bucket": "raw",
                "file": "uploads/lst_of_users_anon_1.csv",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 4
        assert "DATE_DERNIERE_CONNECTION_1" in body["columns"]

    def test_file_not_found_returns_404(self):
        from fastapi import HTTPException
        with patch("app.routers.columns_router.get_file_columns_from_minio",
                   side_effect=HTTPException(status_code=404, detail="Fichier introuvable")):
            response = client.get("/columns", params={"bucket": "raw", "file": "inexistant.csv"})
        assert response.status_code == 404

    def test_missing_params_returns_422(self):
        response = client.get("/columns")
        assert response.status_code == 422


class TestHealthEndpoint:
    def test_health_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSchemas:
    """Tests de validation des schemas Pydantic."""

    def test_valid_request_three_columns(self):
        req = ProcessDateRequest(
            date_columns=["DATE_CREATION", "DATE_DESACTIVATION", "DATE_DERNIERE_CONNECTION_1"],
            date_formats=["MDY", "MDY", "MDY"],
            bucket="raw",
            file="uploads/lst_of_users_anon_1.csv",
        )
        assert len(req.date_columns) == 3

    def test_mismatch_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProcessDateRequest(
                date_columns=["A", "B"],
                date_formats=["MDY"],
                bucket="raw",
                file="test.csv",
            )

    def test_invalid_format_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProcessDateRequest(
                date_columns=["DATE"],
                date_formats=["XYZ"],
                bucket="raw",
                file="test.csv",
            )
