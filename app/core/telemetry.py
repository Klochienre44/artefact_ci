"""
Instrumentation OpenTelemetry -- Traces, Metriques et Logs structures.
Compatible SigNoz via OTLP/gRPC.
"""

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

logger = logging.getLogger("arteci.telemetry")


def setup_telemetry():
    """Configure l'instrumentation OpenTelemetry."""
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from app.core.config import settings

        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment": "production",
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)

        logger.info("OpenTelemetry configure avec succes, endpoint=%s",
                    settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    except Exception as exc:
        # Le demarrage n'est pas bloque si OpenTelemetry est indisponible
        logger.warning("OpenTelemetry non disponible : %s. Demarrage sans observabilite.", exc)


def get_tracer(name: str = "arteci"):
    """Retourne un tracer OpenTelemetry."""
    return trace.get_tracer(name)
