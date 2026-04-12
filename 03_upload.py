#!/usr/bin/env python3
"""
Script 3/3 — Uploader une vidéo doublée sur YouTube.

Utilisation :
    python 03_upload.py "dubbed/Ma Video_dubbed_fr.mp4"

Options :
    --title "Mon titre"           (titre de la vidéo)
    --description "Description"   (description)
    --tags "tag1,tag2,tag3"       (tags séparés par des virgules)
    --category 22                 (catégorie YouTube, 22 = People & Blogs)
    --privacy unlisted            (public, unlisted, private — défaut: private)

Nécessite :
    - Un fichier client_secret.json (credentials OAuth Google)
    - La première exécution ouvrira un navigateur pour l'authentification
"""

import sys
import os
import argparse
import pickle
import time
from pathlib import Path

# ─── Charger la config depuis .env ──────────────────────────────────────────
def load_env():
    """Charge les variables depuis config.env si présent."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), value)

load_env()

# ─── Configuration ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(SCRIPT_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "youtube_token.pickle")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Catégories YouTube courantes :
# 1  = Film & Animation    | 10 = Music
# 15 = Pets & Animals      | 17 = Sports
# 20 = Gaming              | 22 = People & Blogs
# 23 = Comedy              | 24 = Entertainment
# 25 = News & Politics     | 26 = Howto & Style
# 27 = Education           | 28 = Science & Technology
YOUTUBE_CATEGORIES = {
    "film": "1", "music": "10", "gaming": "20", "blogs": "22",
    "comedy": "23", "entertainment": "24", "education": "27",
    "science": "28", "howto": "26", "news": "25", "sports": "17",
}


def authenticate():
    """
    Authentifie l'utilisateur via OAuth 2.0.
    Sauvegarde le token pour les utilisations suivantes.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    credentials = None

    # Charge le token sauvegardé s'il existe
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            credentials = pickle.load(token)

    # Si pas de token valide, lance le flow OAuth
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("🔄 Rafraîchissement du token...")
            credentials.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                print("❌ Fichier client_secret.json introuvable.")
                print(f"   Attendu ici : {CLIENT_SECRET_FILE}")
                print()
                print("   Pour le créer :")
                print("   1. Va sur https://console.cloud.google.com/")
                print("   2. Crée un projet (ou utilise un existant)")
                print("   3. Active l'API 'YouTube Data API v3'")
                print("   4. Va dans 'Identifiants' → 'Créer des identifiants'")
                print("   5. Choisis 'ID client OAuth' → Type 'Application de bureau'")
                print("   6. Télécharge le JSON et renomme-le client_secret.json")
                print("   7. Place-le dans le dossier du script")
                sys.exit(1)

            print("🔐 Ouverture du navigateur pour l'authentification Google...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            credentials = flow.run_local_server(port=0)

        # Sauvegarde le token
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(credentials, token)
        print("✅ Authentification réussie (token sauvegardé)")

    return credentials


def upload_video(filepath: str, title: str, description: str,
                 tags: list, category: str, privacy: str) -> str:
    """
    Upload la vidéo sur YouTube avec reprise automatique (resumable upload).
    Retourne l'ID de la vidéo uploadée.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    credentials = authenticate()
    youtube = build("youtube", "v3", credentials=credentials)

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)

    print(f"\n📤 Upload en cours ({file_size_mb:.1f} Mo)...")
    print(f"   Titre    : {title}")
    print(f"   Privacy  : {privacy}")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category,
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Upload resumable (reprend en cas de coupure réseau)
    media = MediaFileUpload(
        filepath,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 Mo par chunk
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Boucle d'upload avec retry
    response = None
    retry_count = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"   ⬆️  Progression : {progress}%", end="\r")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504] and retry_count < max_retries:
                retry_count += 1
                wait_time = 2 ** retry_count
                print(f"\n   ⚠️  Erreur serveur, retry {retry_count}/{max_retries} dans {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print(f"\n\n✅ Upload terminé !")
    print(f"🎬 URL : {video_url}")
    print(f"🔒 Visibilité : {privacy}")

    if privacy == "private":
        print("\n💡 La vidéo est en mode privé. Pour la rendre publique :")
        print(f"   python 03_upload.py --set-public {video_id}")
        print("   Ou change la visibilité depuis YouTube Studio.")

    return video_id


def main():
    parser = argparse.ArgumentParser(
        description="Uploader une vidéo doublée sur YouTube"
    )
    parser.add_argument("filepath", help="Chemin vers la vidéo à uploader")
    parser.add_argument("--title", default=None, help="Titre de la vidéo")
    parser.add_argument("--description", default="", help="Description de la vidéo")
    parser.add_argument("--tags", default="", help="Tags séparés par des virgules")
    parser.add_argument("--category", default="22", help="ID catégorie YouTube (défaut: 22 = People & Blogs)")
    parser.add_argument(
        "--privacy", default="private",
        choices=["public", "unlisted", "private"],
        help="Visibilité (défaut: private pour sécurité)"
    )

    args = parser.parse_args()

    # Vérifie que le fichier existe
    if not os.path.exists(args.filepath):
        print(f"❌ Fichier introuvable : {args.filepath}")
        sys.exit(1)

    # Vérifie les dépendances
    try:
        import google.auth  # noqa: F401
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
    except ImportError as e:
        print(f"❌ Dépendance manquante : {e}")
        print("   Installe avec : pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    # Titre par défaut = nom du fichier
    title = args.title or Path(args.filepath).stem.replace("_", " ")

    # Tags
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    print("=" * 60)
    print("📺  YouTube Upload Pipeline")
    print("=" * 60)

    video_id = upload_video(
        filepath=args.filepath,
        title=title,
        description=args.description,
        tags=tags,
        category=args.category,
        privacy=args.privacy,
    )

    print(f"\n🎉 Pipeline terminé ! Video ID : {video_id}")


if __name__ == "__main__":
    main()
