#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
#  Setup VPS — Relais multistream IRL (Twitch + YouTube + Kick)
#
#  À lancer sur un VPS Linux fraîchement créé (Ubuntu 22.04/24.04).
#  RECOMMANDÉ : Vultr "Cloud Compute" région Séoul (proche de toi en Corée).
#
#  Usage :
#    1. Crée le VPS, connecte-toi en SSH (ssh root@IP_DU_VPS)
#    2. curl -sSL https://raw.githubusercontent.com/skyyartconcours-ai/dubflow/claude/korea-irl-livestream-setup-JJ1j4/docs/korea-irl-livestream/vps-setup.sh | bash
#       (ou copie ce dossier et lance : bash vps-setup.sh)
# ══════════════════════════════════════════════════════════════════════

set -e

echo ""
echo "════════════════════════════════════════════════════"
echo "  📡 Setup relais multistream IRL"
echo "════════════════════════════════════════════════════"
echo ""

APP_DIR="/opt/irl-relay"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# ── 1. Docker ──
if ! command -v docker &>/dev/null; then
    echo "🐳 Installation de Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

# ── 2. Saisie des clés de stream ──
echo ""
echo "  Récupère tes clés de stream dans chaque dashboard :"
echo "    • Twitch  : dashboard.twitch.tv -> Paramètres -> Stream -> Clé"
echo "    • YouTube : studio.youtube.com -> Créer -> En direct -> Clé"
echo "    • Kick    : kick.com -> Settings -> Stream Key (+ l'URL d'ingest)"
echo ""
read -rp "  Clé Twitch          : " TWITCH_KEY
read -rp "  Clé YouTube         : " YOUTUBE_KEY
read -rp "  Clé Kick            : " KICK_KEY
read -rp "  App Kick (souvent 'app') : " KICK_APP
KICK_APP=${KICK_APP:-app}
read -rp "  Hôte ingest Kick (ex: xxx.global-contribute.live-video.net) : " KICK_INGEST_HOST

# ── 3. Télécharger les fichiers de conf si absents ──
BASE_URL="https://raw.githubusercontent.com/skyyartconcours-ai/dubflow/claude/korea-irl-livestream-setup-JJ1j4/docs/korea-irl-livestream"
[ -f docker-compose.yml ]   || curl -sSL "$BASE_URL/docker-compose.yml"   -o docker-compose.yml
[ -f nginx.conf.template ]  || curl -sSL "$BASE_URL/nginx.conf.template"  -o nginx.conf.template

# ── 4. Générer nginx.conf à partir du template ──
echo "📝 Génération de la configuration..."
sed -e "s|__TWITCH_KEY__|${TWITCH_KEY}|g" \
    -e "s|__YOUTUBE_KEY__|${YOUTUBE_KEY}|g" \
    -e "s|__KICK_KEY__|${KICK_KEY}|g" \
    -e "s|__KICK_APP__|${KICK_APP}|g" \
    nginx.conf.template > nginx.conf

# Fichier d'environnement pour stunnel (hôte Kick)
echo "KICK_INGEST_HOST=${KICK_INGEST_HOST}" > .env

# ── 5. Pare-feu : ouvrir le port RTMP ──
if command -v ufw &>/dev/null; then
    ufw allow 1935/tcp  >/dev/null 2>&1 || true
    ufw allow 8080/tcp  >/dev/null 2>&1 || true
fi

# ── 6. Lancement ──
echo "🚀 Démarrage du relais..."
docker compose up -d

PUBLIC_IP=$(curl -s4 ifconfig.me 2>/dev/null || echo "IP_DU_VPS")

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✅ Relais multistream en ligne !"
echo "════════════════════════════════════════════════════"
echo ""
echo "  Dans ton encodeur, publie le flux vers :"
echo "      rtmp://${PUBLIC_IP}/live/stream"
echo "  (ou, mieux, via l'IP interne du tunnel SpeedFusion : rtmp://10.x.x.x/live/stream)"
echo ""
echo "  📊 Stats en direct : http://${PUBLIC_IP}:8080/stat"
echo ""
echo "  Commandes utiles :"
echo "      docker compose logs -f      # voir les logs / le fan-out"
echo "      docker compose restart      # redémarrer"
echo "      docker compose down         # arrêter (et stopper la facturation Vultr en supprimant le VPS)"
echo ""
echo "════════════════════════════════════════════════════"
