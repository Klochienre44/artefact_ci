"""Configuration centralisee de l'application ARTECI."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_VERSION: str = "1.0.0"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"
    OTEL_SERVICE_NAME: str = "arteci-api"

    # Traitement
    CHUNK_SIZE: int = 100_000
    PREVIEW_ROWS: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
