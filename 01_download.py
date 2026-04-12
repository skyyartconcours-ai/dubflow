#!/usr/bin/env python3
"""
Script 1/3 — Télécharger une vidéo YouTube en qualité maximale.

Utilisation :
    python 01_download.py "https://www.youtube.com/watch?v=XXXXXX"

La vidéo est enregistrée dans le dossier ./downloads/
"""

import sys
import os
import subprocess
import re
import json

# ─── Configuration ──────────────────────────────────────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")


def sanitize_filename(name: str) -> str:
    """Nettoie le nom de fichier pour éviter les caractères problématiques."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name[:200]  # limite la longueur


def get_video_info(url: str) -> dict:
    """Récupère les métadonnées de la vidéo sans la télécharger."""
    cmd = ["yt-dlp", "--dump-json", "--no-playlist", url]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def download_video(url: str) -> str:
    """
    Télécharge la vidéo en qualité maximale (meilleure vidéo + meilleur audio).
    Retourne le chemin du fichier final.
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Récupère les infos pour le nom du fichier
    print("📡 Récupération des informations de la vidéo...")
    info = get_video_info(url)
    title = sanitize_filename(info.get("title", "video"))
    video_id = info.get("id", "unknown")
    duration = info.get("duration_string", "?")
    resolution = info.get("resolution", "?")

    print(f"📹 Titre     : {title}")
    print(f"🆔 ID        : {video_id}")
    print(f"⏱️  Durée     : {duration}")
    print(f"📐 Résolution: {resolution}")
    print()

    # Nom de sortie
    output_template = os.path.join(DOWNLOAD_DIR, f"{title} [{video_id}].%(ext)s")

    # Téléchargement en qualité maximale :
    # - bestvideo : meilleure qualité vidéo disponible
    # - bestaudio : meilleur flux audio
    # - merge en .mp4 (recodage si nécessaire)
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--embed-thumbnail",
        "--embed-subs",
        "--sub-langs", "en,fr",
        "--write-auto-subs",
        "--output", output_template,
        "--progress",
        "--console-title",
        url,
    ]

    print("⬇️  Téléchargement en cours (qualité maximale)...")
    print("─" * 60)
    subprocess.run(cmd, check=True)
    print("─" * 60)

    # Trouve le fichier téléchargé
    for f in os.listdir(DOWNLOAD_DIR):
        if video_id in f and f.endswith(".mp4"):
            filepath = os.path.join(DOWNLOAD_DIR, f)
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"\n✅ Téléchargement terminé !")
            print(f"📁 Fichier : {filepath}")
            print(f"💾 Taille  : {size_mb:.1f} Mo")
            return filepath

    # Fallback : cherche n'importe quel fichier récent
    files = sorted(
        [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR)],
        key=os.path.getmtime,
        reverse=True,
    )
    if files:
        print(f"\n✅ Fichier trouvé : {files[0]}")
        return files[0]

    raise FileNotFoundError("Impossible de trouver le fichier téléchargé.")


def main():
    if len(sys.argv) < 2:
        print("Usage : python 01_download.py <URL_YOUTUBE>")
        print('Exemple : python 01_download.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"')
        sys.exit(1)

    url = sys.argv[1]

    # Vérifie que yt-dlp est installé
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("❌ yt-dlp n'est pas installé.")
        print("   Installe-le avec : pip install yt-dlp")
        print("   Ou via : brew install yt-dlp  (macOS)")
        sys.exit(1)

    # Vérifie que ffmpeg est installé (nécessaire pour le merge)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("⚠️  ffmpeg n'est pas installé (nécessaire pour merger vidéo+audio).")
        print("   Installe-le avec : brew install ffmpeg  (macOS)")
        print("   Ou : sudo apt install ffmpeg  (Linux)")
        sys.exit(1)

    filepath = download_video(url)
    print(f"\n🎬 Prochaine étape : python 02_dub.py \"{filepath}\"")


if __name__ == "__main__":
    main()
