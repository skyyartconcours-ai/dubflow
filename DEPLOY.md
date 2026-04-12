# DubFlow — Déployer en ligne (0 code requis)

## Option recommandée : Railway (5 min)

Railway te donne une URL publique gratuitement (plan Trial = 5$/mois de crédit offert).

### Étapes

**1. Crée un repo GitHub**

- Va sur [github.com/new](https://github.com/new)
- Nomme-le `dubflow` (privé de préférence)
- Upload tous les fichiers du dossier `youtube-dubbing-pipeline/` dans le repo
  (Tu peux drag & drop les fichiers directement sur la page GitHub)

**2. Déploie sur Railway**

- Va sur [railway.com](https://railway.com) et connecte-toi avec GitHub
- Clique **"New Project"** → **"Deploy from GitHub Repo"**
- Sélectionne ton repo `dubflow`
- Railway détecte automatiquement le Dockerfile et lance le build

**3. Ajoute ta clé ElevenLabs**

- Dans Railway, va dans ton service → onglet **"Variables"**
- Ajoute :
  ```
  ELEVENLABS_API_KEY = ta_clé_ici
  ```

**4. Récupère ton URL**

- Railway te donne une URL type `dubflow-production-xxxx.up.railway.app`
- Va dans **Settings → Networking → Generate Domain** si ce n'est pas fait
- C'est cette URL que toi et ta copine utiliserez !

**5. (Optionnel) YouTube Upload**

Pour l'upload YouTube depuis le serveur :
- Place `client_secret.json` dans le repo (ou monte-le comme volume Railway)
- La première authentification devra se faire en local puis uploade le `youtube_token.pickle` généré

---

## Option alternative : Render

- Va sur [render.com](https://render.com)
- **New → Web Service → From GitHub**
- Sélectionne le repo
- Environment: **Docker**
- Ajoute la variable `ELEVENLABS_API_KEY`
- Clique **Create**
- URL fournie automatiquement

---

## Option alternative : ton propre PC (local)

Si tu préfères que ça tourne sur ton PC sans payer :

```bash
cd youtube-dubbing-pipeline
pip install -r requirements.txt
python app.py
```

Ouvre `http://localhost:5000`. Pour que ta copine y accède depuis son téléphone ou PC sur le même Wi-Fi : `http://TON_IP_LOCALE:5000`

---

## Notes importantes

**Stockage** : Les vidéos téléchargées/doublées sont automatiquement supprimées après 48h pour économiser l'espace disque sur le serveur.

**Coûts** :
- Railway : ~5$/mois (plan Hobby) — le trial est gratuit
- ElevenLabs : le dubbing consomme des minutes selon ton plan (Free = ~10 min/mois, Creator = 100 min/mois)
- YouTube API : gratuit (limite de ~6 uploads/jour)

**Sécurité** : L'app n'a pas d'authentification utilisateur. Si tu la mets en ligne, n'importe qui avec l'URL peut l'utiliser. Pour restreindre l'accès :
- Garde le repo GitHub en privé
- Utilise un nom d'URL difficile à deviner
- Ou ajoute une protection par mot de passe (me demander si besoin)
