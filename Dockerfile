# ─────────────────────────────────────────────────────────────────────────────
# ARTECI — Dockerfile multi-stage
# Étape 1 : builder (installe les dépendances)
# Étape 2 : image finale allégée (sans outils de build)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1 : builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Dépendances système minimales pour compiler les wheels Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances dans un répertoire isolé
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2 : image finale ───────────────────────────────────────────────────
FROM python:3.12-slim AS final

LABEL maintainer="ARTECI Team <arteci@esatic.ci>"
LABEL description="ARTECI — API de Standardisation des Dates"
LABEL version="1.0.0"

WORKDIR /arteci

# Copie des dépendances installées depuis le builder
COPY --from=builder /install /usr/local

# Copie du code source de l'application uniquement
COPY app/ ./app/

# Utilisateur non-root pour la sécurité
RUN useradd -m -u 1001 arteci && chown -R arteci:arteci /arteci
USER arteci

# Variables d'environnement par défaut (surchargées par docker-compose ou K8s)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Healthcheck intégré
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Démarrage avec 4 workers Uvicorn (ajustable via variable d'environnement WORKERS)
CMD uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers ${WORKERS:-4} \
    --log-level info \
    --access-log
