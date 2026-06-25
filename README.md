# ARTECI — API de Standardisation des Dates

> **Challenge Technique — Optimisation du Traitement de Données**
> Projet ARTECI · ESATIC — Master 1 MBDS · 2026

---

## Présentation

**ARTECI** est une API REST haute performance développée avec **FastAPI** pour normaliser les colonnes de dates hétérogènes contenues dans des fichiers CSV ou Excel stockés dans **MinIO** (stockage objet S3-compatible).

### Problème résolu

Les fichiers de données contiennent souvent des colonnes de dates dans des formats incohérents :

| Valeur brute            | Format détecté | Résultat normalisé      |
|-------------------------|----------------|-------------------------|
| `01/15/2023`            | MDY            | `15-01-2023 00:00:00`   |
| `15/01/2023`            | DMY            | `15-01-2023 00:00:00`   |
| `2023-01-15T08:30:00Z`  | ISO 8601       | `15-01-2023 08:30:00`   |
| `1686835800`            | Unix (s)       | `15-06-2023 xx:xx:xx`   |
| `15 janvier 2023`       | Littéral FR    | `15-01-2023 00:00:00`   |

**Format de sortie unique** : `JJ-MM-AAAA HH:mm:ss`

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                     Client HTTP                         │
└────────────────┬───────────────────────────────────────┘
                 │ POST /processDate  │  GET /columns
                 ▼
┌────────────────────────────────────────────────────────┐
│              FastAPI (ARTECI API)                       │
│  ┌─────────────────┐  ┌───────────────────────────┐    │
│  │  date_router    │  │      date_service          │    │
│  │  columns_router │  │  (moteur vectorisé Pandas) │    │
│  └─────────────────┘  └───────────────────────────┘    │
│  ┌────────────────────────────────────────────────┐    │
│  │              minio_service                     │    │
│  └────────────────────────────────────────────────┘    │
└───────────────┬────────────────────────┬───────────────┘
                │                        │
                ▼                        ▼
┌───────────────────────┐   ┌────────────────────────────┐
│        MinIO          │   │  OpenTelemetry Collector    │
│  Stockage objet       │   │  (Traces + Métriques)       │
│  S3-compatible        │   └────────────────────────────┘
└───────────────────────┘
```

### Structure du projet

```
arteci/
├── app/
│   ├── main.py                   # Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py             # Configuration (pydantic-settings)
│   │   └── telemetry.py          # OpenTelemetry
│   ├── routers/
│   │   ├── date_router.py        # POST /processDate
│   │   └── columns_router.py     # GET /columns
│   ├── services/
│   │   ├── date_service.py       # Moteur de normalisation vectorisé
│   │   └── minio_service.py      # Client MinIO
│   └── utils/
│       └── schemas.py            # Schémas Pydantic
├── tests/
│   └── test_arteci.py            # Tests unitaires et intégration
├── k8s/
│   ├── deployment.yaml           # Déploiement K8s + HPA
│   ├── service.yaml              # Service + Ingress
│   └── config.yaml               # ConfigMap + Secret + Namespace
├── docker/
│   └── otel-collector-config.yaml
├── .github/
│   └── workflows/
│       └── ci-cd.yml             # Pipeline CI/CD GitHub Actions
├── Dockerfile                    # Multi-stage (builder + final)
├── docker-compose.yml            # Stack locale complète
└── .env.example                  # Variables d'environnement modèle
```

---

## Démarrage rapide

### Prérequis

- Docker 20+ et Docker Compose plugin installés sur la machine
- Zorin OS / Ubuntu : `sudo apt install docker.io docker-compose-plugin curl -y`

### Démarrage avec Docker Compose

```bash
# 1. Cloner le dépôt
git clone https://github.com/VOTRE_ORG/arteci.git
cd arteci

# 2. Copier et configurer les variables d'environnement
cp .env.example .env

# 3. Démarrer tous les services
docker compose up --build

# 4. Vérifier que l'API répond
curl http://localhost:9001/health
```

### Accès aux interfaces

| Interface       | URL                          | Identifiants           |
|-----------------|------------------------------|------------------------|
| API Swagger     | http://localhost:9001/docs   | —                      |
| Healthcheck     | http://localhost:9001/health | —                      |
| Console MinIO   | http://localhost:9101        | minioadmin / minioadmin |

### Upload du fichier CSV dans MinIO

```bash
# Via le script fourni
bash upload_csv.sh ~/Téléchargements/lst_of_users_anon_1.csv

# Ou manuellement via la console http://localhost:9101
# Bucket "raw" → Upload du fichier
```

---

## Endpoints

### `POST /processDate` — Normaliser les colonnes de dates

**Corps de la requête :**

```json
{
  "bucket": "raw",
  "file": "uploads/lst_of_users_anon_1.csv",
  "date_columns": [
    "DATE_CREATION",
    "DATE_DESACTIVATION",
    "DATE_DERNIERE_CONNECTION_1"
  ],
  "date_formats": ["MDY", "MDY", "MDY"]
}
```

| Champ          | Type                    | Description                              |
|----------------|-------------------------|------------------------------------------|
| `bucket`       | string                  | Nom du bucket MinIO                      |
| `file`         | string                  | Chemin du fichier dans le bucket         |
| `date_columns` | list[string]            | Colonnes à normaliser                    |
| `date_formats` | list[DMY\|MDY\|AUTO]    | Format de chaque colonne (même ordre)    |

**Réponse :**

```json
{
  "success": true,
  "file": "uploads/lst_of_users_anon_1.csv",
  "bucket": "raw",
  "rows_processed": 100,
  "columns_normalized": [
    "DATE_CREATION",
    "DATE_DESACTIVATION",
    "DATE_DERNIERE_CONNECTION_1"
  ],
  "preview": [
    {
      "NOM": "Alice",
      "DATE_CREATION": "15-01-2023 00:00:00",
      "DATE_DESACTIVATION": "31-12-2099 00:00:00",
      "DATE_DERNIERE_CONNECTION_1": "01-06-2024 00:00:00"
    }
  ],
  "elapsed_seconds": 0.243
}
```

---

### `GET /columns` — Lister les colonnes d'un fichier

```
GET /columns?bucket=raw&file=uploads/lst_of_users_anon_1.csv
```

**Réponse :**

```json
{
  "file": "uploads/lst_of_users_anon_1.csv",
  "bucket": "raw",
  "columns": [
    "NOM",
    "DATE_CREATION",
    "DATE_DESACTIVATION",
    "DATE_DERNIERE_CONNECTION_1"
  ],
  "count": 4
}
```

---

### `GET /health` — Vérification de l'état

```json
{ "status": "ok", "version": "1.0.0", "service": "arteci-api" }
```

---

## Tests

```bash
# Installation des dépendances
pip install -r requirements.txt --break-system-packages

# Lancer tous les tests
pytest tests/ -v

# Avec couverture
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Formats de dates supportés

| Format            | Exemple                  | Hint  |
|-------------------|--------------------------|-------|
| DMY slash         | `15/06/2023`             | DMY   |
| MDY slash         | `06/15/2023`             | MDY   |
| DMY tiret         | `15-06-2023`             | DMY   |
| Avec heure        | `15/06/2023 14:30:00`    | DMY   |
| ISO 8601          | `2023-06-15T14:30:00Z`   | AUTO  |
| Unix secondes     | `1686835800`             | AUTO  |
| Unix millisecondes| `1686835800000`          | AUTO  |
| Mois littéral FR  | `15 juin 2023`           | AUTO  |

---

## Choix techniques

| Choix                    | Justification                                                      |
|--------------------------|--------------------------------------------------------------------|
| **FastAPI**              | Performances élevées, validation Pydantic native, Swagger intégré  |
| **Pandas vectorisé**     | Traitement en masse sans boucles Python, cache LRU sur les valeurs |
| **MinIO**                | Stockage objet S3-compatible, déployable on-premise                |
| **OpenTelemetry**        | Observabilité standard : traces, métriques et logs structurés      |
| **Docker multi-stage**   | Image finale allégée sans outils de build                          |
| **Kubernetes + HPA**     | Mise à l'échelle automatique selon la charge CPU/mémoire           |

---

## Variables d'environnement

| Variable                       | Défaut                       | Description              |
|--------------------------------|------------------------------|--------------------------|
| `MINIO_ENDPOINT`               | `minio:9000`                 | Adresse MinIO            |
| `MINIO_ACCESS_KEY`             | `minioadmin`                 | Clé d'accès MinIO        |
| `MINIO_SECRET_KEY`             | `minioadmin`                 | Clé secrète MinIO        |
| `OTEL_EXPORTER_OTLP_ENDPOINT`  | `http://otel-collector:4317` | Endpoint OpenTelemetry   |
| `WORKERS`                      | `2`                          | Workers Uvicorn          |
| `CHUNK_SIZE`                   | `100000`                     | Lignes par chunk         |
| `PREVIEW_ROWS`                 | `100`                        | Lignes dans l'aperçu     |

---

## Déploiement Kubernetes

```bash
# Création du namespace et des ressources
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Vérification
kubectl get pods -n arteci-production
kubectl get svc -n arteci-production
```

---

## Pipeline CI/CD

```
push develop  →  lint  →  test  →  build  →  push GHCR  →  deploy staging
push tag vX.Y  →  lint  →  test  →  build  →  push GHCR  →  deploy production
```

---


