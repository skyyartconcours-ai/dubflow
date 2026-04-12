# YouTube Dubbing Pipeline — Guide d'installation

## Pre-requis

- Python 3.9+
- ffmpeg (pour le merge vidéo/audio)

---

## 1. Installer les dépendances

```bash
pip install yt-dlp elevenlabs google-api-python-client google-auth-oauthlib
```

Vérifie aussi que **ffmpeg** est installé :

```bash
# macOS
brew install ffmpeg

# Windows (avec chocolatey)
choco install ffmpeg

# Linux
sudo apt install ffmpeg
```

---

## 2. Configurer ElevenLabs

1. Crée un compte sur [elevenlabs.io](https://elevenlabs.io) (plan Creator minimum recommandé pour le dubbing)
2. Va dans **Settings > API Keys** : [lien direct](https://elevenlabs.io/app/settings/api-keys)
3. Copie ta clé API
4. Colle-la dans `config.env` à la ligne `ELEVENLABS_API_KEY=...`

### Limites du dubbing ElevenLabs

| Plan      | Minutes/mois | Taille max fichier | Durée max |
|-----------|-------------|-------------------|-----------|
| Free      | ~10 min     | 1 Go              | 2h30      |
| Starter   | 30 min      | 1 Go              | 2h30      |
| Creator   | 100 min     | 1 Go              | 2h30      |
| Pro       | 500 min     | 1 Go              | 2h30      |

---

## 3. Configurer YouTube API

### Étape A : Créer un projet Google Cloud

1. Va sur [console.cloud.google.com](https://console.cloud.google.com/)
2. Clique sur **Sélectionner un projet** > **Nouveau projet**
3. Nomme-le (ex: "YouTube Dubbing") et crée-le

### Étape B : Activer l'API YouTube

1. Dans la barre de recherche, tape **YouTube Data API v3**
2. Clique dessus et appuie sur **Activer**

### Étape C : Configurer l'écran de consentement OAuth

1. Va dans **APIs & Services > OAuth consent screen**
2. Choisis **External** (sauf si tu as Google Workspace)
3. Remplis le nom de l'app (ex: "Mon Dubbing Tool")
4. Ajoute ton email
5. Dans **Scopes**, ajoute : `https://www.googleapis.com/auth/youtube.upload`
6. Dans **Test users**, ajoute ton adresse Gmail (celle de ta chaîne YouTube)
7. Publie l'app en mode "Test" (suffisant pour un usage personnel)

### Étape D : Créer les identifiants OAuth

1. Va dans **APIs & Services > Credentials**
2. Clique **Create credentials > OAuth client ID**
3. Type : **Desktop application**
4. Nomme-le (ex: "Dubbing Desktop")
5. **Télécharge le JSON**
6. **Renomme-le** en `client_secret.json`
7. **Place-le** dans le dossier `youtube-dubbing-pipeline/`

---

## 4. Utilisation

### Étape 1 — Télécharger la vidéo

```bash
python 01_download.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

La vidéo est enregistrée dans `./downloads/`

### Étape 2 — Doubler (EN → FR)

```bash
python 02_dub.py "downloads/Nom de la Video [abc123].mp4"
```

Options disponibles :

```bash
# Changer le nombre de locuteurs (si la vidéo a plusieurs personnes)
python 02_dub.py "video.mp4" --speakers 3

# Changer les langues
python 02_dub.py "video.mp4" --source-lang en --target-lang fr
```

La vidéo doublée est enregistrée dans `./dubbed/`

### Étape 3 — Uploader sur YouTube

```bash
python 03_upload.py "dubbed/Video_dubbed_fr.mp4" --title "Mon titre" --privacy private
```

Options disponibles :

```bash
python 03_upload.py "video.mp4" \
  --title "Titre de la vidéo" \
  --description "Description complète ici" \
  --tags "tag1,tag2,tag3" \
  --category 27 \
  --privacy unlisted
```

La première fois, un navigateur s'ouvrira pour l'authentification Google.

---

## Catégories YouTube

| ID | Catégorie           |
|----|---------------------|
| 1  | Film & Animation    |
| 10 | Music               |
| 17 | Sports              |
| 20 | Gaming              |
| 22 | People & Blogs      |
| 23 | Comedy              |
| 24 | Entertainment       |
| 25 | News & Politics     |
| 26 | Howto & Style       |
| 27 | Education           |
| 28 | Science & Technology|

---

## Structure du dossier

```
youtube-dubbing-pipeline/
├── 01_download.py       # Téléchargement YouTube
├── 02_dub.py            # Doublage ElevenLabs
├── 03_upload.py         # Upload YouTube
├── config.env           # Tes clés API
├── client_secret.json   # Credentials Google (à créer)
├── youtube_token.pickle # Token OAuth (créé automatiquement)
├── SETUP.md             # Ce guide
├── downloads/           # Vidéos téléchargées
└── dubbed/              # Vidéos doublées
```

---

## Dépannage

**"yt-dlp n'est pas installé"** → `pip install yt-dlp`

**"ffmpeg n'est pas installé"** → Voir section 1

**"Clé API ElevenLabs manquante"** → Vérifie `config.env`

**"client_secret.json introuvable"** → Voir section 3, étape D

**"Quota YouTube dépassé"** → L'API YouTube a une limite de 10 000 unités/jour. Un upload coûte ~1 600 unités, soit environ 6 uploads/jour.

**Le dubbing est lent** → Normal, ElevenLabs peut prendre 5-15 min selon la durée de la vidéo. Le script attend automatiquement.

**Erreur "Access Not Configured"** → Vérifie que l'API YouTube Data API v3 est bien activée dans Google Cloud Console.
