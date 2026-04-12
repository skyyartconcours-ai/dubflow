#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
#  DubFlow — Installation automatique sur Hetzner VPS
#
#  Usage (une seule commande à copier sur ton serveur) :
#    curl -sSL https://raw.githubusercontent.com/TON_USER/dubflow/main/hetzner-setup.sh | bash
#
#  Ou après avoir cloné le repo :
#    chmod +x hetzner-setup.sh && ./hetzner-setup.sh
# ══════════════════════════════════════════════════════════════════════

set -e

echo ""
echo "════════════════════════════════════════════════════"
echo "  🎬 DubFlow — Installation sur Hetzner"
echo "════════════════════════════════════════════════════"
echo ""

# ── 1. Mise à jour système ──
echo "📦 Mise à jour du système..."
apt-get update -qq
apt-get upgrade -y -qq

# ── 2. Installer Docker ──
if ! command -v docker &> /dev/null; then
    echo "🐳 Installation de Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "   ✅ Docker installé"
else
    echo "   ✅ Docker déjà installé"
fi

# ── 3. Installer Docker Compose ──
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "🐳 Installation de Docker Compose..."
    apt-get install -y -qq docker-compose-plugin
    echo "   ✅ Docker Compose installé"
else
    echo "   ✅ Docker Compose déjà installé"
fi

# ── 4. Créer le dossier de l'app ──
APP_DIR="/opt/dubflow"
mkdir -p $APP_DIR
cd $APP_DIR

# ── 5. Créer docker-compose.yml ──
echo "📝 Création de la configuration Docker..."

cat > docker-compose.yml << 'COMPOSE_EOF'
services:
  dubflow:
    build: .
    container_name: dubflow
    restart: unless-stopped
    ports:
      - "80:5000"
    volumes:
      - dubflow-data:/app/data
      - ./client_secret.json:/app/client_secret.json:ro
    environment:
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      - DATA_DIR=/app/data
      - SECRET_KEY=${SECRET_KEY:-dubflow-prod-key}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  dubflow-data:
COMPOSE_EOF

# ── 6. Demander la clé ElevenLabs ──
echo ""
echo "════════════════════════════════════════════════════"
echo "  🔑 Configuration"
echo "════════════════════════════════════════════════════"

if [ -z "$ELEVENLABS_API_KEY" ]; then
    echo ""
    echo "  Entre ta clé API ElevenLabs"
    echo "  (récupère-la sur https://elevenlabs.io/app/settings/api-keys)"
    echo ""
    read -p "  Clé API : " ELEVENLABS_KEY
    echo ""
else
    ELEVENLABS_KEY=$ELEVENLABS_API_KEY
fi

# Créer le fichier .env
SECRET=$(openssl rand -hex 16)
cat > .env << ENV_EOF
ELEVENLABS_API_KEY=${ELEVENLABS_KEY}
SECRET_KEY=${SECRET}
ENV_EOF

chmod 600 .env

# ── 7. Cloner le repo (si pas déjà fait) ──
if [ ! -f "app.py" ]; then
    echo "📥 Téléchargement de l'application..."
    if [ -n "$DUBFLOW_REPO" ]; then
        git clone "$DUBFLOW_REPO" /tmp/dubflow-src
        cp -r /tmp/dubflow-src/* $APP_DIR/
        rm -rf /tmp/dubflow-src
    else
        echo ""
        echo "  ⚠️  Copie les fichiers du projet dans $APP_DIR"
        echo "  Ou relance avec: DUBFLOW_REPO=https://github.com/ton_user/dubflow.git ./hetzner-setup.sh"
        echo ""
        echo "  Si tu as déjà les fichiers ici, appuie sur Entrée pour continuer."
        read -p "  " _
    fi
fi

# ── 8. Créer un placeholder client_secret.json si absent ──
if [ ! -f "client_secret.json" ]; then
    echo '{}' > client_secret.json
    echo "  ⚠️  client_secret.json vide créé — remplace-le par le vrai pour l'upload YouTube"
fi

# ── 9. Build et lancement ──
echo ""
echo "🏗️  Construction de l'image Docker (ça peut prendre 2-3 min)..."
docker compose build --quiet

echo "🚀 Lancement de DubFlow..."
docker compose up -d

# ── 10. Vérification ──
echo ""
echo "⏳ Vérification du démarrage..."
sleep 5

if docker compose ps | grep -q "running"; then
    # Récupérer l'IP publique
    PUBLIC_IP=$(curl -s4 ifconfig.me 2>/dev/null || echo "ton-ip")

    echo ""
    echo "════════════════════════════════════════════════════"
    echo "  ✅ DubFlow est en ligne !"
    echo "════════════════════════════════════════════════════"
    echo ""
    echo "  🌐 URL : http://${PUBLIC_IP}"
    echo ""
    echo "  📁 Dossier : ${APP_DIR}"
    echo "  🔑 Config  : ${APP_DIR}/.env"
    echo ""
    echo "  Commandes utiles :"
    echo "    docker compose logs -f     # voir les logs"
    echo "    docker compose restart     # redémarrer"
    echo "    docker compose down        # arrêter"
    echo ""
    echo "  Pour YouTube : remplace client_secret.json par"
    echo "  le vrai fichier depuis Google Cloud Console."
    echo ""
    echo "════════════════════════════════════════════════════"
else
    echo "  ❌ Erreur au démarrage. Vérifie avec : docker compose logs"
fi
