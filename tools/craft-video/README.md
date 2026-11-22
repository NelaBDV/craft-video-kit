# Outils partagés T3 Code — `craft-video`

Dossier partagé des scripts et bibliothèques réutilisables pour les projets d’animation 2D et de clips musicaux (EffectCraft + FilmCraft) dans T3 Code.

## Contenu

| Fichier | Rôle | Utilisé par |
| :--- | :--- | :--- |
| [ec_runtime.py](./ec_runtime.py) | Constructeur JSX EffectCraft (`JsxBuilder`), nul caméra ancre `[0,0]` (`makeCamNull`), calcul `cam_focus()`, formes vectorielles/Bézier, lueurs/ombres, keyframes lissées/hold, runner CLI | `craft-2d-animation`, `craft-music-video` |
| [audio_cues.py](./audio_cues.py) | Analyse audio 44,1 kHz sans dérive (`hop = 441` = 10 ms exact), inspection de la fin de piste, découpe de tranches d’écoute à l’oreille, génération du squelette `lyrics_timing.json` | `craft-music-video` |
| [lyrics_overlay.py](./lyrics_overlay.py) | Validation de `lyrics_timing.json` (rapport des repères `"uncertain": true`) et génération des compositions paroles transparentes RGBA (`L01_...`, sans bandeau noir) | `craft-music-video` |
| [render_ec_batch.sh](./render_ec_batch.sh) | Rendu séquentiel basse consommation EffectCraft (ProRes HQ RGB + ProRes 4444 RGBA), reprise intelligente via `ffprobe`, bridage CPU/RAM (`nice`, `ionice`, `RAYON_NUM_THREADS`, `taskset`) | `craft-2d-animation`, `craft-music-video` |
| [assemble_filmcraft.py](./assemble_filmcraft.py) | Assemblage timeline FilmCraft (avec ou sans audio, piste `V2` alpha optionnelle) et double export synchronisé Master + Clean (en gardant le texte diégétique sur `V1`) | `craft-2d-animation`, `craft-music-video` |

## Dépendances système

- **Python 3.9+** (bibliothèque standard uniquement — aucune dépendance pip requise)
- **`ffmpeg` et `ffprobe`** (analyse audio 44,1 kHz, découpe d’écoute, vérification des rendus)
- **EffectCraft CLI** (`effectcraft-cli` natif ou Flatpak `ai.storyteller.effectcraft`)
- **FilmCraft CLI** (`filmcraft-cli` natif ou Flatpak `ai.storyteller.filmcraft`)
- Optionnels Linux pour le mode basse charge : `nice`, `ionice`, `taskset`

## Exemples rapides

```bash
# 1. Vérifier les outils installés (sans lancer de rendu)
python3 ~/.t3/shared/craft-video/ec_runtime.py --check-env

# 2. Analyser une piste audio et extraire des tranches d’écoute à l’oreille
python3 ~/.t3/shared/craft-video/audio_cues.py analyze ./audio/track.mp3 --bpm 122 --first-beat 0.61
python3 ~/.t3/shared/craft-video/audio_cues.py slice ./audio/track.mp3 --out-dir ./previews/audio_slices --segment-sec 18 --overlap-sec 2

# 3. Valider lyrics_timing.json et lister les repères incertains
python3 ~/.t3/shared/craft-video/lyrics_overlay.py --timing ./audio/lyrics_timing.json --validate

# 4. Vérifier un plan de rendu EffectCraft en mode --dry-run (séquentiel basse charge)
~/.t3/shared/craft-video/render_ec_batch.sh \
  --project ./projects/clip.ecproj --out-dir ./renders_vfx \
  --rgb V01_Intro,V02_Main --rgba L01_Intro,L02_Main --threads 2 --cores 0-3 --dry-run

# 5. Vérifier un assemblage FilmCraft Master + Clean en mode --dry-run
python3 ~/.t3/shared/craft-video/assemble_filmcraft.py \
  --out-fcproj ./projects/clip.fcproj --timing ./audio/lyrics_timing.json \
  --renders-dir ./renders_vfx --export-master ./exports/clip_lyrics.mp4 \
  --export-clean ./exports/clip_clean.mp4 --dry-run
```
