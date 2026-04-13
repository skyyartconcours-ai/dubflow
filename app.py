#!/usr/bin/env python3
"""
DubFlow — YouTube Dubbing Pipeline (v2 - Dual Audio)
Webapp déployable sur Hetzner / Railway / VPS.

Pipeline complet :
  1. Télécharge la vidéo YouTube (qualité max, yt-dlp)
  2. Envoie à ElevenLabs pour le doublage (garde la voix du créateur)
  3. Fusionne les 2 pistes audio (original + doublée) avec ffmpeg
  4. Upload sur YouTube avec les 2 langues disponibles
"""

import os
import json
import time
import uuid
import pickle
import subprocess
import threading
import re
import shutil
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, Response, send_from_directory

# ─── Chemins ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")
DUBBED_DIR = os.path.join(DATA_DIR, "dubbed")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(DATA_DIR, "youtube_token.pickle")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

for d in [DOWNLOAD_DIR, DUBBED_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── App Flask ──────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = os.environ.get("SECRET_KEY", "dubflow-" + uuid.uuid4().hex[:12])

# Stockage en mémoire des jobs
jobs = {}


# ═══════════════════════════════════════════════════════════════════════════
#  Utilitaires
# ═══════════════════════════════════════════════════════════════════════════

def get_elevenlabs_key() -> str:
    """Récupère la clé ElevenLabs : env var > settings.json."""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if key:
        return key
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            return data.get("elevenlabs_api_key", "")
        except Exception:
            pass
    return ""


def save_settings_file(data: dict):
    """Persiste les paramètres dans settings.json (survit aux redémarrages)."""
    existing = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(data)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    return name.strip('. ')[:180]


def update_job(job_id: str, **kwargs):
    if job_id in jobs:
        jobs[job_id].update(kwargs)
        jobs[job_id]["updated_at"] = time.time()


def cleanup_old_files(directory: str, max_age_hours: int = 72):
    """Supprime les fichiers de plus de max_age_hours."""
    try:
        now = time.time()
        for f in os.listdir(directory):
            fp = os.path.join(directory, f)
            if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > max_age_hours * 3600:
                os.remove(fp)
    except Exception:
        pass


def run_ffmpeg(args: list, timeout: int = 300) -> subprocess.CompletedProcess:
    """Exécute ffmpeg avec gestion d'erreur."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extrait la piste audio d'une vidéo en .m4a (AAC)."""
    result = run_ffmpeg([
        "-i", video_path,
        "-vn",              # pas de vidéo
        "-acodec", "copy",  # copie le codec audio sans ré-encoder
        output_path,
    ])
    return result.returncode == 0 and os.path.exists(output_path)


def create_dual_audio_video(
    original_video: str,
    dubbed_video: str,
    output_path: str,
    primary_lang: str = "fra",
    secondary_lang: str = "eng",
) -> bool:
    """
    Crée une vidéo avec 2 pistes audio :
      - Piste 1 (primary) : audio de la vidéo doublée (ex: français)
      - Piste 2 (secondary) : audio de la vidéo originale (ex: anglais)
    Prend la vidéo de l'original (meilleure qualité).
    """
    result = run_ffmpeg([
        "-i", original_video,
        "-i", dubbed_video,
        "-map", "0:v:0",             # vidéo de l'original (qualité max)
        "-map", "1:a:0",             # audio du doublage (piste principale)
        "-map", "0:a:0",             # audio original (piste secondaire)
        "-c:v", "copy",              # pas de ré-encodage vidéo
        "-c:a", "aac",               # encode les 2 pistes en AAC
        "-b:a:0", "192k",            # bitrate piste 1
        "-b:a:1", "192k",            # bitrate piste 2
        "-metadata:s:a:0", f"language={primary_lang}",
        "-metadata:s:a:0", "title=Francais",
        "-metadata:s:a:1", f"language={secondary_lang}",
        "-metadata:s:a:1", "title=English",
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-movflags", "+faststart",   # optimise le streaming
        output_path,
    ], timeout=600)
    return result.returncode == 0 and os.path.exists(output_path)


# ═══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 1 : Téléchargement YouTube
# ═══════════════════════════════════════════════════════════════════════════

def download_video(job_id: str, url: str) -> str | None:
    """
    Télécharge une vidéo YouTube en qualité max.
    Met à jour le job avec la progression.
    Retourne le chemin du fichier ou None en cas d'erreur.
    """
    cleanup_old_files(DOWNLOAD_DIR)
    update_job(job_id, step="download", status="fetching_info",
               message="Récupération des infos vidéo...")

    # ── Métadonnées ──
    try:
        cmd = ["yt-dlp", "--dump-json", "--no-playlist", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            err = result.stderr[:300] if result.stderr else "URL invalide ou vidéo indisponible"
            update_job(job_id, status="error", message=f"Erreur: {err}")
            return None
        info = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        update_job(job_id, status="error", message="Timeout : la vidéo n'a pas répondu à temps")
        return None
    except json.JSONDecodeError:
        update_job(job_id, status="error", message="Impossible de lire les infos de la vidéo")
        return None

    title = sanitize_filename(info.get("title", "video"))
    video_id = info.get("id", "unknown")
    duration = info.get("duration_string", "?")
    thumbnail = info.get("thumbnail", "")
    duration_sec = info.get("duration", 0)

    # Limite de sécurité : 2h30 max (limite ElevenLabs)
    if duration_sec > 9000:
        update_job(job_id, status="error",
                   message=f"Vidéo trop longue ({duration}). Maximum : 2h30 pour le doublage.")
        return None

    update_job(job_id, status="downloading",
               message=f"Téléchargement de \"{title}\"...",
               title=title, video_id=video_id, duration=duration, thumbnail=thumbnail)

    output_template = os.path.join(DOWNLOAD_DIR, f"{title} [{video_id}].%(ext)s")

    # ── Téléchargement qualité max ──
    cmd = [
        "yt-dlp", "--no-playlist",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--newline",
        url,
    ]

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            line = line.strip()
            if "[download]" in line and "%" in line:
                match = re.search(r'(\d+\.?\d*)%', line)
                if match:
                    pct = float(match.group(1))
                    update_job(job_id, progress=round(pct * 0.25, 1),
                               message=f"Téléchargement : {pct:.0f}%")
        process.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        process.kill()
        update_job(job_id, status="error", message="Timeout : téléchargement trop long")
        return None

    if process.returncode != 0:
        update_job(job_id, status="error", message="Erreur yt-dlp lors du téléchargement")
        return None

    # ── Retrouver le fichier ──
    filepath = None
    for f in os.listdir(DOWNLOAD_DIR):
        if video_id in f and f.endswith(".mp4"):
            filepath = os.path.join(DOWNLOAD_DIR, f)
            break

    if not filepath:
        mp4s = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith(".mp4")]
        if mp4s:
            filepath = max(mp4s, key=os.path.getmtime)

    if not filepath or not os.path.exists(filepath):
        update_job(job_id, status="error", message="Fichier introuvable après téléchargement")
        return None

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    update_job(job_id, progress=25,
               message=f"Téléchargé ({size_mb:.0f} Mo)",
               filepath=filepath, filename=os.path.basename(filepath), size_mb=round(size_mb, 1))

    return filepath


# ═══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 2 : Doublage ElevenLabs
# ═══════════════════════════════════════════════════════════════════════════

def dub_video(job_id: str, filepath: str, source_lang: str,
              target_lang: str, num_speakers: int) -> str | None:
    """
    Envoie le fichier à ElevenLabs pour le doublage.
    Retourne le chemin du fichier doublé ou None.
    """
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        update_job(job_id, status="error",
                   message="SDK ElevenLabs non installé (pip install elevenlabs)")
        return None

    api_key = get_elevenlabs_key()
    if not api_key:
        update_job(job_id, status="error",
                   message="Clé API ElevenLabs non configurée — ouvre les Paramètres (engrenage en bas à droite)")
        return None

    client = ElevenLabs(api_key=api_key)

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb > 1024:
        update_job(job_id, status="error",
                   message="Fichier trop volumineux (max 1 Go pour ElevenLabs)")
        return None

    # ── Envoi à ElevenLabs ──
    update_job(job_id, step="dub", status="uploading",
               message=f"Envoi à ElevenLabs ({file_size_mb:.0f} Mo)...", progress=30)

    try:
        with open(filepath, "rb") as f:
            response = client.dubbing.create(
                file=f,
                name=f"DubFlow - {Path(filepath).stem[:60]}",
                source_lang=source_lang,
                target_lang=target_lang,
                num_speakers=num_speakers,
            )
    except Exception as e:
        msg = str(e)[:300]
        if "401" in msg or "auth" in msg.lower():
            update_job(job_id, status="error",
                       message="Clé API ElevenLabs invalide. Vérifie dans les Paramètres.")
        elif "quota" in msg.lower() or "limit" in msg.lower():
            update_job(job_id, status="error",
                       message="Quota ElevenLabs dépassé. Vérifie ton plan sur elevenlabs.io.")
        else:
            update_job(job_id, status="error", message=f"Erreur ElevenLabs : {msg}")
        return None

    dubbing_id = response.dubbing_id
    update_job(job_id, status="processing", dubbing_id=dubbing_id,
               message="Doublage en cours chez ElevenLabs...", progress=35)

    # ── Polling ──
    start_time = time.time()
    max_wait = 3600  # 1h max
    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            update_job(job_id, status="error", message="Timeout : le doublage prend trop longtemps")
            return None

        try:
            metadata = client.dubbing.get(dubbing_id)
        except Exception as e:
            # Retry silencieux sur erreur réseau
            time.sleep(15)
            continue

        status = metadata.status
        minutes, seconds = divmod(int(elapsed), 60)

        if status == "dubbed":
            update_job(job_id, progress=70,
                       message=f"Doublage terminé en {minutes}m{seconds:02d}s ! Téléchargement...")
            break
        elif status == "failed":
            error = getattr(metadata, "error", "Erreur inconnue")
            update_job(job_id, status="error", message=f"Échec du doublage : {error}")
            return None
        else:
            est = min(35 + (elapsed / 8), 68)
            update_job(job_id, progress=round(est, 1),
                       message=f"Doublage en cours... {minutes}m{seconds:02d}s")
            time.sleep(12)

    # ── Télécharger le résultat ──
    cleanup_old_files(DUBBED_DIR)
    base_name = sanitize_filename(Path(filepath).stem)
    output_filename = f"{base_name}_dubbed_{target_lang}.mp4"
    output_path = os.path.join(DUBBED_DIR, output_filename)

    try:
        with open(output_path, "wb") as f:
            for chunk in client.dubbing.get_dubbed_file(dubbing_id, target_lang):
                f.write(chunk)
    except Exception as e:
        update_job(job_id, status="error",
                   message=f"Erreur lors du téléchargement du résultat : {str(e)[:200]}")
        return None

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        update_job(job_id, status="error", message="Le fichier doublé est vide ou corrompu")
        return None

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    update_job(job_id, progress=75,
               message=f"Fichier doublé récupéré ({size_mb:.0f} Mo)",
               dubbed_filepath=output_path, dubbed_filename=output_filename,
               dubbed_size_mb=round(size_mb, 1))

    return output_path


# ═══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 3 : Fusion double piste audio
# ════════════════════════════════════════════════════════════════════════════

def merge_dual_audio(job_id: str, original_path: str, dubbed_path: str,
                     target_lang: str = "fra", source_lang: str = "eng") -> dict | None:
    """
    Crée une vidéo avec 2 pistes audio + extrait les audios séparément.
    Retourne un dict avec les chemins des fichiers ou None.
    """
    update_job(job_id, step="merge", status="merging",
               message="Fusion des 2 pistes audio...", progress=78)

    base_name = sanitize_filename(Path(original_path).stem)
    cleanup_old_files(OUTPUT_DIR)

    # Chemins de sortie
    dual_video = os.path.join(OUTPUT_DIR, f"{base_name}_dual_audio.mp4")
    audio_primary = os.path.join(OUTPUT_DIR, f"{base_name}_audio_{target_lang}.m4a")
    audio_secondary = os.path.join(OUTPUT_DIR, f"{base_name}_audio_{source_lang}.m4a")

    # ── Extraire l'audio doublé (piste primaire pour l'audience FR) ──
    update_job(job_id, message="Extraction de l'audio doublé...", progress=80)
    if not extract_audio(dubbed_path, audio_primary):
        update_job(job_id, status="error", message="Erreur ffmpeg : impossible d'extraire l'audio doublé")
        return None

    # ── Extraire l'audio original ──
    update_job(job_id, message="Extraction de l'audio original...", progress=83)
    if not extract_audio(original_path, audio_secondary):
        update_job(job_id, status="error", message="Erreur ffmpeg : impossible d'extraire l'audio original")
        return None

    # ── Créer la vidéo dual audio ──
    update_job(job_id, message="Création de la vidéo double piste...", progress=86)
    dual_ok = create_dual_audio_video(
        original_video=original_path,
        dubbed_video=dubbed_path,
        output_path=dual_video,
        primary_lang=target_lang[:3],
        secondary_lang=source_lang[:3],
    )

    if not dual_ok:
        # Fallback : utilise la vidéo doublée simple
        update_job(job_id, message="Fallback : utilisation de la vidéo doublée simple", progress=88)
        shutil.copy2(dubbed_path, dual_video)

    # ── Vérification ──
    files = {
        "dual_video": dual_video if os.path.exists(dual_video) else dubbed_path,
        "audio_primary": audio_primary if os.path.exists(audio_primary) else None,
        "audio_secondary": audio_secondary if os.path.exists(audio_secondary) else None,
        "original_video": original_path,
        "dubbed_video": dubbed_path,
    }

    sizes = {}
    for key, path in files.items():
        if path and os.path.exists(path):
            sizes[f"{key}_size_mb"] = round(os.path.getsize(path) / (1024 * 1024), 1)
            sizes[f"{key}_filename"] = os.path.basename(path)

    update_job(job_id, progress=90,
               message="Fusion terminée !",
               **files, **sizes)

    return files


# ═══════════════════════════════════════════════════════════════════════════
#  PIPELINE COMPLET (Mode Rapide)
# ═══════════════════════════════════════════════════════════════════════════

def _run_full_pipeline(job_id: str, url: str, source_lang: str,
                       target_lang: str, num_speakers: int):
    """Thread du pipeline complet : download → dub → merge."""
    try:
        # ÉTAPE 1 : Téléchargement
        original_path = download_video(job_id, url)
        if not original_path:
            return  # l'erreur est déjà dans le job

        # ÉTAPE 2 : Doublage
        dubbed_path = dub_video(job_id, original_path, source_lang, target_lang, num_speakers)
        if not dubbed_path:
            return

        # ÉTAPE 3 : Fusion double piste
        lang_map = {"en": "eng", "fr": "fra", "es": "spa", "de": "deu",
                     "pt": "por", "ja": "jpn", "ko": "kor", "zh": "zho"}
        files = merge_dual_audio(
            job_id, original_path, dubbed_path,
            target_lang=lang_map.get(target_lang, target_lang),
            source_lang=lang_map.get(source_lang, source_lang),
        )
        if not files:
            return

        # ── Résultat final ──
        dual = files.get("dual_video", dubbed_path)
        size_mb = round(os.path.getsize(dual) / (1024 * 1024), 1) if os.path.exists(dual) else 0

        update_job(
            job_id,
            step="done", status="done", progress=100,
            message=f"Pipeline terminé ! Vidéo double piste prête ({size_mb} Mo)",
            final_video=dual,
            final_filename=os.path.basename(dual),
            final_size_mb=size_mb,
        )

    except Exception as e:
        update_job(job_id, status="error", message=f"Erreur inattendue : {str(e)[:300]}")


# ═══════════════════════════════════════════════════════════════════════════
#  ÉTAPES SÉPARÉES (Mode Avancé)
# ═══════════════════════════════════════════════════════════════════════════

def _run_download_only(job_id: str, url: str):
    """Thread de téléchargement seul."""
    try:
        filepath = download_video(job_id, url)
        if filepath:
            size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 1)
            update_job(job_id, status="done", progress=100,
                       message=f"Téléchargé ! ({size_mb} Mo)",
                       filepath=filepath, filename=os.path.basename(filepath), size_mb=size_mb)
    except Exception as e:
        update_job(job_id, status="error", message=str(e)[:300])


def _run_dub_only(job_id: str, filepath: str, source_lang: str,
                  target_lang: str, num_speakers: int):
    """Thread de doublage seul."""
    try:
        dubbed_path = dub_video(job_id, filepath, source_lang, target_lang, num_speakers)
        if dubbed_path:
            size_mb = round(os.path.getsize(dubbed_path) / (1024 * 1024), 1)
            update_job(job_id, status="done", progress=100,
                       message=f"Doublage terminé ! ({size_mb} Mo)",
                       filepath=dubbed_path, filename=os.path.basename(dubbed_path), size_mb=size_mb)
    except Exception as e:
        update_job(job_id, status="error", message=str(e)[:300])


def _run_merge_only(job_id: str, original_path: str, dubbed_path: str,
                    source_lang: str, target_lang: str):
    """Thread de fusion audio seul."""
    try:
        lang_map = {"en": "eng", "fr": "fra", "es": "spa", "de": "deu",
                     "pt": "por", "ja": "jpn", "ko": "kor", "zh": "zho"}
        files = merge_dual_audio(
            job_id, original_path, dubbed_path,
            target_lang=lang_map.get(target_lang, target_lang),
            source_lang=lang_map.get(source_lang, source_lang),
        )
        if files:
            dual = files.get("dual_video", dubbed_path)
            size_mb = round(os.path.getsize(dual) / (1024 * 1024), 1)
            update_job(job_id, status="done", progress=100,
                       message=f"Fusion terminée ! ({size_mb} Mo)",
                       filepath=dual, filename=os.path.basename(dual), size_mb=size_mb)
    except Exception as e:
        update_job(job_id, status="error", message=str(e)[:300])


def _run_upload(job_id: str, filepath: str, title: str, description: str,
                tags: list, category: str, privacy: str):
    """Thread d'upload YouTube."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        update_job(job_id, status="error",
                   message="Dépendances Google manquantes (pip install google-api-python-client google-auth-oauthlib)")
        return

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    try:
        update_job(job_id, step="upload", status="authenticating",
                   message="Authentification YouTube...", progress=5)

        credentials = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "rb") as token:
                credentials = pickle.load(token)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                with open(TOKEN_FILE, "wb") as token:
                    pickle.dump(credentials, token)
            else:
                if not os.path.exists(CLIENT_SECRET_FILE):
                    update_job(job_id, status="error",
                               message="client_secret.json manquant. Place-le dans le dossier du projet (voir guide SETUP.md).")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                credentials = flow.run_local_server(port=0)
                with open(TOKEN_FILE, "wb") as token:
                    pickle.dump(credentials, token)

        youtube = build("youtube", "v3", credentials=credentials)

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        update_job(job_id, status="uploading",
                   message=f"Upload en cours ({file_size_mb:.0f} Mo)...", progress=10)

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

        media = MediaFileUpload(filepath, mimetype="video/mp4",
                                resumable=True, chunksize=10 * 1024 * 1024)

        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                update_job(job_id, progress=pct, message=f"Upload : {pct}%")

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        update_job(job_id, status="done", progress=100,
                   message="Upload terminé !",
                   video_id=video_id, video_url=video_url)

    except Exception as e:
        update_job(job_id, status="error", message=f"Erreur upload : {str(e)[:300]}")


# ═══════════════════════════════════════════════════════════════════════════
#  Routes API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "2.0"})


# ── Pipeline complet (Mode Rapide) ──
@app.route("/api/pipeline", methods=["POST"])
def api_pipeline():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL manquante"}), 400

    source_lang = data.get("source_lang", "en")
    target_lang = data.get("target_lang", "fr")
    num_speakers = int(data.get("num_speakers", 1))

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "pipeline", "status": "starting",
        "step": "download", "message": "Démarrage...", "progress": 0,
        "url": url, "source_lang": source_lang, "target_lang": target_lang,
        "created_at": time.time(), "updated_at": time.time(),
    }

    threading.Thread(
        target=_run_full_pipeline,
        args=(job_id, url, source_lang, target_lang, num_speakers),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id})


# ── Étapes séparées (Mode Avancé) ──
@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL manquante"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "download", "status": "starting",
        "message": "Démarrage...", "progress": 0,
        "created_at": time.time(), "updated_at": time.time(),
    }
    threading.Thread(target=_run_download_only, args=(job_id, url), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/dub", methods=["POST"])
def api_dub():
    data = request.json
    filepath = data.get("filepath", "").strip()
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "Fichier introuvable"}), 400

    source_lang = data.get("source_lang", "en")
    target_lang = data.get("target_lang", "fr")
    num_speakers = int(data.get("num_speakers", 1))

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "dub", "status": "starting",
        "message": "Démarrage du doublage...", "progress": 0,
        "created_at": time.time(), "updated_at": time.time(),
    }
    threading.Thread(
        target=_run_dub_only,
        args=(job_id, filepath, source_lang, target_lang, num_speakers),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/merge", methods=["POST"])
def api_merge():
    data = request.json
    original = data.get("original_filepath", "").strip()
    dubbed = data.get("dubbed_filepath", "").strip()
    if not original or not os.path.exists(original):
        return jsonify({"error": "Fichier original introuvable"}), 400
    if not dubbed or not os.path.exists(dubbed):
        return jsonify({"error": "Fichier doublé introuvable"}), 400

    source_lang = data.get("source_lang", "en")
    target_lang = data.get("target_lang", "fr")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "merge", "status": "starting",
        "message": "Démarrage de la fusion...", "progress": 0,
        "created_at": time.time(), "updated_at": time.time(),
    }
    threading.Thread(
        target=_run_merge_only,
        args=(job_id, original, dubbed, source_lang, target_lang),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    data = request.json
    filepath = data.get("filepath", "")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "Fichier introuvable"}), 400

    title = data.get("title", "Vidéo doublée")
    description = data.get("description", "")
    tags = [t.strip() for t in data.get("tags", "").split(",") if t.strip()]
    category = data.get("category", "22")
    privacy = data.get("privacy", "private")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "upload", "status": "starting",
        "message": "Démarrage de l'upload...", "progress": 0,
        "created_at": time.time(), "updated_at": time.time(),
    }
    threading.Thread(
        target=_run_upload,
        args=(job_id, filepath, title, description, tags, category, privacy),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


# ── Status / Files ──
@app.route("/api/job/<job_id>")
def api_job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify(job)


@app.route("/api/files/<folder>")
def api_list_files(folder):
    dir_map = {"downloads": DOWNLOAD_DIR, "dubbed": DUBBED_DIR, "output": OUTPUT_DIR}
    target_dir = dir_map.get(folder)
    if not target_dir or not os.path.exists(target_dir):
        return jsonify([])

    files = []
    for f in sorted(os.listdir(target_dir),
                    key=lambda x: os.path.getmtime(os.path.join(target_dir, x)),
                    reverse=True):
        fp = os.path.join(target_dir, f)
        if os.path.isfile(fp):
            files.append({
                "filename": f, "filepath": fp,
                "size_mb": round(os.path.getsize(fp) / (1024 * 1024), 1),
                "date": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%d/%m/%Y %H:%M"),
            })
    return jsonify(files)


# ── Settings ──
@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    api_key = get_elevenlabs_key()
    has_key = bool(api_key)
    has_yt = os.path.exists(CLIENT_SECRET_FILE)
    has_token = os.path.exists(TOKEN_FILE)

    # Check ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        has_ffmpeg = True
    except Exception:
        has_ffmpeg = False

    # Check yt-dlp
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5)
        has_ytdlp = True
    except Exception:
        has_ytdlp = False

    return jsonify({
        "elevenlabs_configured": has_key,
        "elevenlabs_key_preview": f"...{api_key[-6:]}" if has_key and len(api_key) > 6 else "",
        "youtube_client_secret": has_yt,
        "youtube_authenticated": has_token,
        "ffmpeg_installed": has_ffmpeg,
        "ytdlp_installed": has_ytdlp,
    })


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.json
    key = data.get("elevenlabs_api_key", "").strip()
    if key:
        os.environ["ELEVENLABS_API_KEY"] = key
        save_settings_file({"elevenlabs_api_key": key})
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
#  Lancement
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=" * 55)
    print("  🎬  DubFlow v2 — Dual Audio Pipeline")
    print("=" * 55)
    print(f"  🌐 http://localhost:{port}")
    print(f"  📁 Data : {DATA_DIR}")
    print("=" * 55)

    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
