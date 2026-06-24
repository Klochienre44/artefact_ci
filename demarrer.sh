#!/bin/bash
# =============================================================================
# ARTECI -- Script de demarrage automatique
# Compatible Zorin OS / Ubuntu
# Usage : bash demarrer.sh
# =============================================================================

set -e

BLEU='\033[0;34m'
VERT='\033[0;32m'
JAUNE='\033[1;33m'
ROUGE='\033[0;31m'
NC='\033[0m'

titre()  { echo -e "\n${BLEU}══════════════════════════════════════════${NC}"; echo -e "${BLEU}  $1${NC}"; echo -e "${BLEU}══════════════════════════════════════════${NC}"; }
succes() { echo -e "${VERT}  OK  $1${NC}"; }
info()   { echo -e "${JAUNE}  >>  $1${NC}"; }
erreur() { echo -e "${ROUGE}  ERR $1${NC}"; }

echo -e "${BLEU}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   ARTECI -- Demarrage automatique   ║"
echo "  ║   API disponible sur port 9001      ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# -- 1. Verification de Docker ------------------------------------------------
titre "1. Verification de Docker"
if ! command -v docker &> /dev/null; then
    erreur "Docker n'est pas installe."
    info "Installation en cours..."
    sudo apt-get update -qq
    sudo apt-get install -y docker.io docker-compose-plugin curl
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker "$USER"
    succes "Docker installe. Fermez et rouvrez le terminal, puis relancez : bash demarrer.sh"
    exit 0
fi
succes "Docker trouve : $(docker --version | awk '{print $3}' | tr -d ',')"

if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    succes "Docker Compose v2 disponible"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
    succes "Docker Compose v1 disponible"
else
    erreur "Docker Compose introuvable."
    info "Installation : sudo apt install docker-compose-plugin -y"
    exit 1
fi

# -- 2. Verification des ports ------------------------------------------------
titre "2. Verification des ports"
for PORT in 9001 9100 9101 4317; do
    if ss -tulpn 2>/dev/null | grep -q ":$PORT "; then
        info "Port $PORT deja utilise -- sera remplace au demarrage"
    else
        succes "Port $PORT libre"
    fi
done

# -- 3. Nettoyage des anciens conteneurs --------------------------------------
titre "3. Nettoyage des anciens conteneurs ARTECI"
$COMPOSE_CMD down --remove-orphans 2>/dev/null || true
succes "Nettoyage effectue"

# -- 4. Construction de l'image Docker ----------------------------------------
titre "4. Construction de l'image Docker"
info "Premiere construction : 2 a 3 minutes (telechargement des images de base)"
$COMPOSE_CMD build --no-cache

# -- 5. Demarrage des services ------------------------------------------------
titre "5. Demarrage de tous les services"
info "Services : arteci-api + minio + minio-init + otel-collector"
$COMPOSE_CMD up -d

# -- 6. Attente que l'API soit prete ------------------------------------------
titre "6. Attente du demarrage de l'API"
MAX=90
COMPTEUR=0
echo -n "  Attente"
until curl -sf http://localhost:9001/health > /dev/null 2>&1; do
    echo -n "."
    sleep 3
    COMPTEUR=$((COMPTEUR + 3))
    if [ $COMPTEUR -ge $MAX ]; then
        echo ""
        erreur "L'API n'a pas demarre en $MAX secondes."
        info "Consulter les logs : $COMPOSE_CMD logs arteci-api"
        exit 1
    fi
done
echo ""
succes "API operationnelle !"

# -- 7. Resume ----------------------------------------------------------------
titre "ARTECI est pret !"
echo ""
echo -e "  ${VERT}API ARTECI (Swagger)${NC}  -->  http://localhost:9001/docs"
echo -e "  ${VERT}Healthcheck${NC}           -->  http://localhost:9001/health"
echo -e "  ${VERT}Console MinIO${NC}         -->  http://localhost:9101"
echo -e "  ${VERT}Login MinIO${NC}           -->  minioadmin / minioadmin"
echo ""
echo -e "  ${JAUNE}Etape suivante : uploader le fichier CSV${NC}"
echo -e "  ${JAUNE}bash upload_csv.sh ~/Telechargements/lst_of_users_anon_1.csv${NC}"
echo ""
echo -e "  ${BLEU}Commandes utiles :${NC}"
echo -e "  ${BLEU}  Logs en direct : $COMPOSE_CMD logs -f arteci-api${NC}"
echo -e "  ${BLEU}  Arreter        : $COMPOSE_CMD down${NC}"
echo -e "  ${BLEU}  Redemarrer     : $COMPOSE_CMD restart arteci-api${NC}"
echo ""
