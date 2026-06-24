#!/bin/bash
# =============================================================================
# ARTECI -- Upload d'un fichier CSV dans MinIO (bucket raw)
# Usage : bash upload_csv.sh /chemin/vers/fichier.csv
# =============================================================================

VERT='\033[0;32m'
JAUNE='\033[1;33m'
ROUGE='\033[0;31m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${ROUGE}Usage : bash upload_csv.sh /chemin/vers/fichier.csv${NC}"
    echo -e "${JAUNE}Exemple : bash upload_csv.sh ~/Telechargements/lst_of_users_anon_1.csv${NC}"
    exit 1
fi

FICHIER="$1"
NOM=$(basename "$FICHIER")

if [ ! -f "$FICHIER" ]; then
    echo -e "${ROUGE}Fichier introuvable : $FICHIER${NC}"
    exit 1
fi

echo -e "${JAUNE}Upload de '$NOM' dans MinIO (bucket: raw/uploads/)...${NC}"

# Detecter le nom du reseau Docker Compose (varie selon le nom du dossier)
NETWORK=$(docker network ls --format "{{.Name}}" | grep "arteci" | head -1)
if [ -z "$NETWORK" ]; then
    echo -e "${ROUGE}Reseau Docker ARTECI introuvable. Verifier que les services sont demarres : bash demarrer.sh${NC}"
    exit 1
fi

docker run --rm \
    --network "$NETWORK" \
    -v "$FICHIER:/tmp/$NOM:ro" \
    minio/mc:RELEASE.2024-11-17T19-35-25Z \
    /bin/sh -c "
        mc alias set local http://minio:9000 minioadmin minioadmin --quiet;
        mc mb --ignore-existing local/raw;
        mc cp /tmp/$NOM local/raw/uploads/$NOM;
        echo 'Upload termine.';
    "

echo ""
echo -e "${VERT}Fichier disponible dans MinIO : raw/uploads/$NOM${NC}"
echo ""
echo -e "${JAUNE}Corps JSON pour POST /processDate :${NC}"
echo '{
  "bucket": "raw",
  "file": "uploads/'"$NOM"'",
  "date_columns": ["DATE_CREATION", "DATE_DESACTIVATION", "DATE_DERNIERE_CONNECTION_1"],
  "date_formats": ["MDY", "MDY", "MDY"]
}'
echo ""
echo -e "${JAUNE}Swagger : http://localhost:9001/docs${NC}"
