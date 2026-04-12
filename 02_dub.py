#!/usr/bin/env python3
"""
Script 2/3 — Doubler une vidéo via l'API ElevenLabs (EN → FR).

Utilisation :
    python 02_dub.py "downloads/Ma Video [abc123].mp4"

Options :
    --source-lang en     (langue source, défaut: en)
    --target-lang fr     (langue cible, défaut: fr)
    --speakers 1         (nombre de locuteurs, défaut: 1)
    --name "Mon projet"  (nom du projet dans ElevenLabs)

La vidéo doublée est enregistrée dans ./dubbed/
Nécessite la clé API ElevenLabs dans config.env ou en variable d'environnement.
"""

import sys
import os
import time
import argparse
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
DUBBED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dubbed")
POLL_INTERVAL = 15  # secondes entre chaque vérification du statut


def get_api_key() -> str:
    """Récupère la clé API ElevenLabs."""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        print("❌ Clé API ElevenLabs manquante.")
        print("   Ajoute-la dans config.env : ELEVENLABS_API_KEY=ta_clé_ici")
        print("   Ou exporte-la : export ELEVENLABS_API_KEY=ta_clé_ici")
        sys.exit(1)
    return key


def create_dubbing(filepath: str, source_lang: str, target_lang: str,
                   num_speakers: int, project_name: str) -> str:
    """
    Envoie le fichier vidéo à l'API ElevenLabs pour dubbing.
    Retourne le dubbing_id.
    """
    from elevenlabs.client import ElevenLabs

    api_key = get_api_key()
    client = ElevenLabs(api_key=api_key)

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"📤 Envoi du fichier à ElevenLabs ({file_size_mb:.1f} Mo)...")
    print(f"   Source : {source_lang} → Cible : {target_lang}")
    print(f"   Locuteurs : {num_speakers}")
    print()

    # ── Limite de taille : 1 Go max via l'API ──
    if file_size_mb > 1024:
        print("⚠️  Le fichier dépasse 1 Go. ElevenLabs limite à 1 Go / 2h30.")
        print("   Considère réduire la qualité ou couper la vidéo.")
        sys.exit(1)

    with open(filepath, "rb") as f:
        response = client.dubbing.create(
            file=f,
            name=project_name,
            source_lang=source_lang,
            target_lang=target_lang,
            num_speakers=num_speakers,
            # watermark=False,  # décommente si ton plan le permet
        )

    dubbing_id = response.dubbing_id
    print(f"✅ Dubbing lancé ! ID : {dubbing_id}")
    return dubbing_id


def wait_for_completion(dubbing_id: str) -> dict:
    """
    Attend que le dubbing soit terminé en interrogeant l'API.
    Retourne les métadonnées du dubbing.
    """
    from elevenlabs.client import ElevenLabs

    api_key = get_api_key()
    client = ElevenLabs(api_key=api_key)

    print(f"\n⏳ En attente de la fin du dubbing (vérification toutes les {POLL_INTERVAL}s)...")
    start_time = time.time()

    while True:
        metadata = client.dubbing.get(dubbing_id)
        status = metadata.status

        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        if status == "dubbed":
            print(f"\n✅ Dubbing terminé en {minutes}m{seconds:02d}s !")
            return metadata
        elif status == "failed":
            error = getattr(metadata, "error", "Erreur inconnue")
            print(f"\n❌ Le dubbing a échoué : {error}")
            sys.exit(1)
        else:
            print(f"   [{minutes:02d}:{seconds:02d}] Statut : {status}...", end="\r")
            time.sleep(POLL_INTERVAL)


def download_dubbed_file(dubbing_id: str, target_lang: str, original_name: str) -> str:
    """
    Télécharge le fichier doublé depuis l'API ElevenLabs.
    Retourne le chemin du fichier sauvegardé.
    """
    from elevenlabs.client import ElevenLabs

    api_key = get_api_key()
    client = ElevenLabs(api_key=api_key)

    os.makedirs(DUBBED_DIR, exist_ok=True)

    # Nom du fichier de sortie
    base_name = Path(original_name).stem
    output_filename = f"{base_name}_dubbed_{target_lang}.mp4"
    output_path = os.path.join(DUBBED_DIR, output_filename)

    print(f"\n📥 Téléchargement du fichier doublé...")

    # L'API retourne un itérateur de bytes
    with open(output_path, "wb") as f:
        for chunk in client.dubbing.get_dubbed_file(dubbing_id, target_lang):
            f.write(chunk)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Fichier doublé sauvegardé !")
    print(f"📁 Fichier : {output_path}")
    print(f"💾 Taille  : {size_mb:.1f} Mo")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Doubler une vidéo via ElevenLabs (EN → FR)"
    )
    parser.add_argument("filepath", help="Chemin vers la vidéo à doubler")
    parser.add_argument("--source-lang", default="en", help="Langue source (défaut: en)")
    parser.add_argument("--target-lang", default="fr", help="Langue cible (défaut: fr)")
    parser.add_argument("--speakers", type=int, default=1, help="Nombre de locuteurs (défaut: 1)")
    parser.add_argument("--name", default=None, help="Nom du projet ElevenLabs")

    args = parser.parse_args()

    # Vérifie que le fichier existe
    if not os.path.exists(args.filepath):
        print(f"❌ Fichier introuvable : {args.filepath}")
        sys.exit(1)

    # Vérifie que le SDK ElevenLabs est installé
    try:
        import elevenlabs  # noqa: F401
    except ImportError:
        print("❌ Le SDK ElevenLabs n'est pas installé.")
        print("   Installe-le avec : pip install elevenlabs")
        sys.exit(1)

    # Nom du projet
    project_name = args.name or f"Dub - {Path(args.filepath).stem}"

    print("=" * 60)
    print("🎙️  ElevenLabs Dubbing Pipeline")
    print("=" * 60)
    print(f"📹 Vidéo    : {args.filepath}")
    print(f"🌍 Langues  : {args.source_lang} → {args.target_lang}")
    print(f"👥 Speakers : {args.speakers}")
    print(f"📋 Projet   : {project_name}")
    print("=" * 60)

    # Étape 1 : Envoyer à ElevenLabs
    dubbing_id = create_dubbing(
        filepath=args.filepath,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        num_speakers=args.speakers,
        project_name=project_name,
    )

    # Étape 2 : Attendre la fin du dubbing
    wait_for_completion(dubbing_id)

    # Étape 3 : Télécharger le résultat
    output_path = download_dubbed_file(
        dubbing_id=dubbing_id,
        target_lang=args.target_lang,
        original_name=args.filepath,
    )

    print(f"\n🎬 Prochaine étape : python 03_upload.py \"{output_path}\"")


if __name__ == "__main__":
    main()
