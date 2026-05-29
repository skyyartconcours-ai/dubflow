# 🎥🇰🇷 Setup Live Stream IRL Corée — Peplink + FusionHub + Multistream

Guide complet pour streamer en IRL (en marchant/transport) en Corée **sans coupure**,
avec **le meilleur son**, et en diffusant **simultanément sur Twitch, YouTube et Kick**.

---

## 1. Architecture

```
                          ┌─ SIM 1 (SKT) ─┐
 [Osmo Pocket 4]          │               │
       │ USB-C (UVC)      ├─ SIM 2 (KT)  ─┤  SpeedFusion
       ▼                  │               │  (bonding + hot failover)
 [Encodeur: phone /       ├─ WiFi/4G     ─┤        │
  mini-PC Larix/OBS] ────▶│  Peplink     ─┘        ▼
   RTMP/SRT local         │  MAX BR1/Transit │   [VPS Séoul : FusionHub]
                          └──────────────────┘        │  flux "recollé", propre
                                                       ▼
                                          [VPS Séoul : relais nginx-rtmp]
                                                       │  fan-out
                                       ┌───────────────┼───────────────┐
                                       ▼               ▼               ▼
                                    Twitch          YouTube           Kick
```

**Le principe anti-coupure :** SpeedFusion duplique/répartit les paquets sur **plusieurs réseaux
à la fois**. Si SKT lâche dans un tunnel de métro, KT a déjà les paquets → **zéro coupure visible**.
Le VPS « recolle » tout et renvoie un flux propre, qui est ensuite diffusé sur les 3 plateformes.

> 💡 En Corée, prends **2 SIM d'opérateurs différents** (ex. SKT + KT) pour une vraie
> redondance réseau, pas 2 SIM du même opérateur.

---

## 2. Liste de matériel

| Élément | Modèle recommandé | Prix indicatif |
|---|---|---|
| Routeur bonding | **Peplink MAX BR1 Mini** (5G : *BR1 Pro 5G*) | ~250-600 € |
| Caméra | **DJI Osmo Pocket 4** | (déjà à toi) |
| Encodeur | Smartphone récent (app **Larix Broadcaster**) ou mini-PC | 0-300 € |
| Micro | **DJI Mic 3** (voir §6) | ~330 € le kit 2 TX |
| SIM data | 2× SIM coréennes (SKT + KT), forfait data | ~20-40 €/mois chacune |
| Batterie | Powerbank USB-C PD 100 W (le bonding consomme) | ~60 € |
| VPS | **Vultr Cloud Compute, région Séoul** | ~0,03 €/h (~12 €/mois) |

---

## 3. Choix du VPS — ⚠️ PAS Hetzner ici

Le repo utilise Hetzner pour l'app de doublage, et c'est très bien **là-bas** (la latence
n'a aucune importance pour du traitement vidéo en différé).

**Pour du live IRL, c'est différent : la latence compte énormément.** Hetzner n'a **aucun
datacenter en Asie** (Allemagne, Finlande, USA) → ~250-300 ms depuis la Corée, ce qui ajoute
un délai énorme et fragilise le tunnel.

➡️ **Prends un VPS dans un datacenter proche de toi :**

| Fournisseur | Région idéale | Latence depuis Séoul |
|---|---|---|
| **Vultr** ✅ (recommandé) | **Séoul** | ~5-15 ms |
| Linode/Akamai | Tokyo / Osaka | ~25-35 ms |
| AWS Lightsail | Séoul (ap-northeast-2) | ~5-15 ms |
| ~~Hetzner~~ ❌ | (Asie indisponible) | ~250 ms+ |

**Taille :** un VPS à **1-2 vCPU / 2-4 Go RAM** suffit largement (le relais RTMP ne
transcode pas, il ne fait que recopier le flux). Sur Vultr, le plan à ~12 €/mois est parfait.
Tu peux le **supprimer après chaque session** pour ne payer qu'à l'heure.

---

## 4. Partie A — Le VPS (bonding + multistream)

Tu as **deux couches** sur le VPS : (A1) le **FusionHub** qui termine le tunnel SpeedFusion,
et (A2) le **relais nginx-rtmp** qui diffuse sur les 3 plateformes.

### A1. FusionHub (termine le bonding)

FusionHub est l'image VM gratuite de Peplink (**licence FusionHub Solo** = 1 routeur connecté,
suffisant pour toi).

1. Crée le VPS Vultr (Séoul) — au moment du choix de l'OS, sélectionne **"Upload ISO" / image
   personnalisée** et charge l'image **FusionHub** (`.img`/`.vhd`) téléchargée sur
   [le portail Peplink InControl2](https://www.peplink.com/products/fusionhub/).
2. Démarre la VM, note son **IP publique**.
3. Va sur InControl2 → **FusionHub** → installe la **licence Solo (gratuite)**.
4. Crée un **profil SpeedFusion** (PepVPN) : tu obtiens un **Serial / ID** + une clé pré-partagée.
   Garde-les pour la config du routeur (§5).

> Pas envie de gérer l'image FusionHub ? Voir l'**alternative 100 % open-source (SRTLA)** au §8 :
> le bonding est alors fait par l'encodeur et le VPS ne fait tourner qu'un récepteur SRT — c'est
> ça qui est entièrement automatisable par script, et qui marche même sur Hetzner.

### A2. Relais multistream (automatisé ✅)

C'est la partie que le script installe tout seul. Sur le VPS :

```bash
curl -sSL https://raw.githubusercontent.com/skyyartconcours-ai/dubflow/claude/korea-irl-livestream-setup-JJ1j4/docs/korea-irl-livestream/vps-setup.sh | bash
```

Le script :
- installe Docker,
- te demande tes **clés de stream** (Twitch / YouTube / Kick),
- génère la config nginx-rtmp + stunnel (Kick exige du RTMPS),
- lance le relais et t'affiche **l'URL où publier ton flux**.

Tu publies **un seul** flux → il part automatiquement vers **les trois** plateformes.

Fichiers fournis dans ce dossier :
- [`vps-setup.sh`](./vps-setup.sh) — installateur
- [`docker-compose.yml`](./docker-compose.yml) — stack (nginx-rtmp + stunnel Kick)
- [`nginx.conf.template`](./nginx.conf.template) — config du fan-out

---

## 5. Partie B — Configuration du Peplink (SpeedFusion)

Config de départ, étape par étape, dans l'interface web du routeur (`http://192.168.50.1`) :

1. **Mise à jour firmware** : Système → Firmware → installe la dernière version.
2. **Insère les 2 SIM** (slots A et B). Va dans **Network → Cellular** :
   - Active les 2 modems, mets-les **tous les deux "Always connect"**.
   - Renseigne l'APN de chaque opérateur si non auto-détecté.
3. **(Optionnel) WiFi WAN** : Network → WiFi WAN, ajoute un réseau WiFi comme 3ᵉ lien.
4. **Priorité des liens** : Network → WAN → mets les 2 SIM (et le WiFi) sur la **même
   priorité (Priority 1)** → c'est ce qui active le **bonding** (et pas juste le failover).
5. **Crée le profil SpeedFusion** : Advanced → SpeedFusion → **New Profile** :
   - Remote ID / Serial = celui du **FusionHub** (§A1),
   - colle la **clé pré-partagée**,
   - **Bonding** : coche **"WAN Smoothing"** = *Normal* (ou *High* dans les zones difficiles —
     ça duplique les paquets pour le hot failover = anti-coupure),
   - **"FEC" (Forward Error Correction)** : *Moderate* → corrige les pertes sans retransmission.
6. **Vérifie le tunnel** : Status → SpeedFusion doit afficher **"Connected"** avec les 2-3 WAN actifs.
7. **Route le flux** : dans ton encodeur, vise l'**IP interne du tunnel** du relais
   (`rtmp://10.x.x.x/live/stream`) plutôt que l'IP publique → tout passe dans le tunnel bondé.

### Réglages anti-coupure recommandés
| Réglage | Valeur | Pourquoi |
|---|---|---|
| WAN Smoothing | Normal → High | Duplique les paquets sur tous les liens (hot failover) |
| FEC | Moderate | Récupère les paquets perdus sans attendre de retransmission |
| Latency cutoff | ~150 ms | Écarte un lien trop lent avant qu'il ne gâche le flux |
| Bitrate stream | 4500-6000 kbps (1080p) | Marge de sécurité vs débit mobile réel |

---

## 6. Partie C — Le son : quel micro DJI ? (comparatif)

Bonne nouvelle : l'**Osmo Pocket 4** se connecte **en direct** aux micros DJI via **OsmoAudio**,
**sans récepteur** (tu mets l'émetteur en mode appairage, il apparaît dans la barre de volume du
Pocket 4). Tu gagnes en poids et en simplicité — idéal en IRL.

### Comparatif DJI Mic 3 vs Mic 2 vs Mic Mini

| Critère | **DJI Mic 3** 🏆 | DJI Mic 2 | DJI Mic Mini |
|---|---|---|---|
| Enregistrement interne | ✅ 32 bits flottant, **32 Go** | ✅ 32 bits flottant, 8 Go | ❌ aucun |
| Qualité audio | 32-bit float | 32-bit float | 24 bits |
| Portée | **400 m** | 250 m | 400 m |
| Réduction de bruit | **2 niveaux** + Adaptive Gain | on/off | oui (1 niveau) |
| Timecode | ✅ (sync parfaite multi-cam) | ❌ | ❌ |
| Capacité | **4 émetteurs + 7 récepteurs** | 2 TX / 1 RX | 2 TX / 1 RX |
| Poids émetteur | **16 g** | 28 g | ~10 g (le + léger) |
| Autonomie | TX 8 h / RX 10 h (+10 h boîtier) | jusqu'à 18 h avec boîtier | la meilleure |
| Prix | ~€€€ | ~€€ | ~€ (le moins cher) |

> ⚠️ Précision : **« DJI Mic 3 Mini » n'existe pas** comme produit distinct. La gamme actuelle
> = **Mic 3**, **Mic 2**, et **Mic Mini**. (Un testeur a surnommé le Mic 3 « le Mic Mini 2
> déguisé » à cause de sa petite taille, d'où la confusion.)

### 🏆 Recommandation : **DJI Mic 3**

**Pourquoi pour ton usage IRL en Corée :**
1. **Enregistrement de secours 32 bits flottant** dans l'émetteur (32 Go) : même si le stream
   coupe, tu gardes un son parfait, récupérable au montage quelle que soit la fois où ça a saturé.
2. **Réduction de bruit à 2 niveaux + Adaptive Gain** : en ville/rue/métro bondé (Séoul = bruyant),
   c'est exactement ce qu'il faut — le gain s'ajuste tout seul quand tu passes du calme au bruyant.
3. **Plus léger (16 g)** et **400 m de portée** : tu peux t'éloigner de la caméra sans décrochage.
4. **Connexion directe au Pocket 4** (OsmoAudio) : pas de récepteur à trimballer.

**Quand choisir autre chose :**
- **Budget serré** → **DJI Mic Mini** : excellent rapport qualité/prix, ultra-léger, super
  autonomie. Limite : **pas d'enregistrement interne** ni de 32-bit float (donc pas de filet de
  sécurité audio si le stream coupe) et réduction de bruit moins fine.
- **Tu as déjà un Mic 2** → garde-le, la différence ne justifie pas forcément le rachat ; le Mic 2
  a aussi l'enregistrement 32-bit float interne.

### Conseils son IRL (tous micros)
- **Bonnette anti-vent (deadcat) obligatoire** en extérieur/marche.
- Micro **sur toi** (poitrine), jamais le micro de la caméra (trop d'écho/ambiance).
- Active la **réduction de bruit** + garde l'**enregistrement interne** comme filet de sécurité.

---

## 7. Partie D — Encodeur & Osmo Pocket 4

Le Pocket 4 est une **caméra**, pas un encodeur de streaming bondé. Schéma le plus fiable :

1. **Pocket 4 → smartphone** en **webcam USB-C (UVC)**, ou Pocket 4 en HDMI vers un mini-PC.
2. Sur le téléphone : **Larix Broadcaster** (gratuit) → encode en **SRT** ou **RTMP** et publie
   vers l'IP du relais **à travers le routeur Peplink** (le bonding est transparent).
3. Réglages encodeur : **1080p / 30 fps / 4500-6000 kbps**, audio **AAC 160 kbps 48 kHz**.

> En SRT, mets une **latence de 2000-4000 ms** côté encodeur : c'est le "buffer" qui absorbe
> les micro-coupures réseau et lisse le rendu.

---

## 8. Alternative 100 % open-source (sans FusionHub) — SRTLA

Si tu veux éviter la licence/l'image FusionHub (et c'était ton idée initiale de « coder le soft
qui fait pareil ») :

- **Encodeur** : un mini-PC **BELABOX** ou l'app **Larix** avec **SRTLA** → c'est l'encodeur qui
  fait le bonding en répartissant le flux SRT sur les modems.
- **VPS** : fait tourner **`srtla_rec`** + un récepteur SRT (MediaMTX), puis le même relais
  nginx-rtmp pour le multistream.
- Avantage : **gratuit**, scriptable, marche sur n'importe quel VPS (même Hetzner). Inconvénient :
  bonding au niveau applicatif (un peu moins robuste que SpeedFusion sous très forte charge), et
  il faut des modems/clés 4G séparés côté encodeur.

Dis-moi si tu veux ce chemin-là et je te génère le script `srtla` correspondant.

---

## 9. Checklist de test avant le live (à faire AVANT la Corée)

- [ ] Les 2 SIM se connectent et apparaissent en **Priority 1** (bonding actif).
- [ ] Tunnel SpeedFusion **"Connected"** vers le FusionHub.
- [ ] **Test de coupure** : débranche/désactive une SIM en plein stream → l'image **ne doit pas
      bouger** (hot failover OK).
- [ ] Le flux apparaît bien sur **Twitch + YouTube + Kick** simultanément (page `:8080/stat`).
- [ ] Micro DJI 3 : réduction de bruit ON, enregistrement interne ON.
- [ ] Powerbank chargée + câbles de rechange.

---

## 10. Récap des coûts

| Poste | Coût |
|---|---|
| VPS Vultr Séoul | ~0,03 €/h (~12 €/mois, ou à l'usage) |
| FusionHub Solo | **gratuit** (1 routeur) |
| Relais multistream | **gratuit** (open-source) |
| SIM data ×2 | ~40-80 €/mois selon forfaits |
| Matériel (one-shot) | Peplink + Mic 3 + batterie |

---

## Sources (specs micros, vérifiées mai 2026)
- [DJI — Comparatif officiel gamme Mic](https://www.dji.com/products/comparison-mic)
- [Heliguy — DJI Mic 3 vs Mic Mini vs Mic 2](https://www.heliguy.com/blogs/posts/dji-mic-3-vs-mic-mini-vs-mic-2/)
- [Heliguy — Connecter l'Osmo Pocket 4 au DJI Mic 3/2/Mini](https://www.heliguy.com/blogs/knowledge-base/how-do-i-connect-osmo-pocket-4-to-dji-mic-3-mic-2-mic-mini/)
- [TechRadar — DJI Mic 3 vs DJI Mic 2](https://www.techradar.com/cameras/camera-accessories/dji-mic-3-vs-dji-mic-2-i-tested-two-flagship-wireless-mics-and-theres-one-clear-winner)
- [DJI — Mic 3 FAQ](https://www.dji.com/mic-3/faq)
