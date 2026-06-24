"""Schemas Pydantic definissant les contrats d'interface des endpoints ARTECI."""

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ProcessDateRequest(BaseModel):
    """Corps de la requete POST /processDate."""

    date_columns: list[str] = Field(
        ...,
        min_length=1,
        description="Liste des noms de colonnes a normaliser.",
        examples=[["DATE_CREATION", "DATE_DESACTIVATION", "DATE_DERNIERE_CONNECTION_1"]],
    )
    date_formats: list[Literal["DMY", "MDY", "AUTO"]] = Field(
        ...,
        min_length=1,
        description=(
            "Format de chaque colonne, dans le meme ordre que date_columns. "
            "DMY = Jour/Mois/Annee (format francais), "
            "MDY = Mois/Jour/Annee (format anglais), "
            "AUTO = detection automatique."
        ),
        examples=[["MDY", "MDY", "MDY"]],
    )
    bucket: str = Field(
        ...,
        description="Nom du bucket MinIO contenant le fichier.",
        examples=["raw"],
    )
    file: str = Field(
        ...,
        description="Chemin complet du fichier dans le bucket MinIO.",
        examples=["uploads/lst_of_users_anon_1.csv"],
    )

    @model_validator(mode="after")
    def validate_columns_and_formats_length(self):
        if len(self.date_columns) != len(self.date_formats):
            raise ValueError(
                f"date_columns et date_formats doivent avoir la meme longueur. "
                f"Recu : {len(self.date_columns)} colonnes pour {len(self.date_formats)} formats."
            )
        return self


class ProcessDateResponse(BaseModel):
    """Reponse de POST /processDate."""

    success: bool = Field(..., description="Indique si le traitement s'est bien deroule.")
    file: str = Field(..., description="Chemin du fichier traite dans MinIO.")
    bucket: str = Field(..., description="Nom du bucket MinIO.")
    rows_processed: int = Field(..., description="Nombre total de lignes traitees.")
    columns_normalized: list[str] = Field(..., description="Liste des colonnes normalisees.")
    preview: list[dict] = Field(
        ...,
        description="Les 100 premieres lignes du fichier apres traitement.",
    )
    elapsed_seconds: float = Field(..., description="Duree totale du traitement en secondes.")


class ColumnsRequest(BaseModel):
    """Parametres de la requete GET /columns."""

    bucket: str = Field(..., description="Nom du bucket MinIO.", examples=["raw"])
    file: str = Field(
        ...,
        description="Chemin complet du fichier dans le bucket.",
        examples=["uploads/lst_of_users_anon_1.csv"],
    )


class ColumnsResponse(BaseModel):
    """Reponse de GET /columns."""

    file: str = Field(..., description="Chemin du fichier.")
    bucket: str = Field(..., description="Nom du bucket.")
    columns: list[str] = Field(..., description="Liste des noms de colonnes du fichier.")
    count: int = Field(..., description="Nombre total de colonnes.")
