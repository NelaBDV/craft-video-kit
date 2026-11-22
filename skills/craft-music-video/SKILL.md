---
name: craft-music-video
description: >-
  Orchestrate FilmCraft and EffectCraft together via MCP (and CLI fallbacks) to
  produce beat-synchronized music videos: ear-verified 44.1 kHz audio/BPM
  breakdown, editable lyrics_timing.json with uncertain-cue flags, short
  storyboard validation, independent transparent RGBA lyrics overlays,
  narrative drawn actions during instrumental passages (no generic waveforms),
  dual Lyrics/Clean 1080p export, and audio+muted QA. Use whenever the user asks
  to create, edit, sync, or render a music video or audio-reactive visuals using
  FilmCraft and EffectCraft.
---

# Craft Music Video (`FilmCraft` + `EffectCraft`)

Workflow réutilisable pour produire des vidéoclips synchronisés sur une piste audio en combinant **EffectCraft** (scènes 2D, motion graphics, VFX, calque paroles alpha indépendant) et **FilmCraft** (montage principal multi-pistes, synchro rythmique, mixage/master audio, étalonnage global, double export Master + Clean).

> **Méthodes d’animation 2D communes** (cadrages, changements de pose avec anticipation, ancres personnages/caméras, pièges de parenting EffectCraft, ordre d’empilement et lisibilité du texte) : suivre **[craft-2d-animation](../craft-2d-animation/SKILL.md)**.
>
> **Référence complète MCP, commandes moteur vérifiées et configurations Flatpak** : [references/mcp-and-commands.md](./references/mcp-and-commands.md).

---

## 0. Pré-requis MCP et Sandbox (à vérifier avant de démarrer)

1. Vérifier que les serveurs MCP `effectcraft` et `filmcraft` sont exposés dans la session courante (ou basculer proprement sur les CLI `effectcraft-cli` / `filmcraft-cli`).
   - S’ils manquent, ne pas inventer d’appels : consulter [references/mcp-and-commands.md](./references/mcp-and-commands.md) pour la configuration exacte (Flatpak Linux `ai.storyteller.filmcraft` / `ai.storyteller.effectcraft` ou binaire natif, en mode **headless** ou **bridge**).
2. **Attention Flatpak (Linux)** : par défaut, `ai.storyteller.effectcraft` n’a accès qu’à `xdg-documents`, `xdg-pictures` et `xdg-videos`. Si le projet réside ailleurs (ex. `~/.t3/projects/...`), passer `--filesystem=<racine_projet>` ou configurer l’override :
   `flatpak override --user --filesystem=home ai.storyteller.effectcraft`
3. **Conflit GUI vs Headless** : ne **jamais** ouvrir le même `.ecproj` ou `.fcproj` simultanément dans l’application graphique et en MCP/CLI headless. Utiliser `--bridge` pour piloter une fenêtre ouverte.

---

## 1. Répartition des rôles : EffectCraft vs FilmCraft

| Domaine | EffectCraft (`.ecproj`) | FilmCraft (`.fcproj`) |
| :--- | :--- | :--- |
| **Usage principal** | Scènes 2D animées (`V01..Vnn`), paroles sur calques transparents indépendants (`L01..Lnn`), titres cinétiques, particules, compositing 2D/3D | Montage principal multi-pistes (`V1` scènes + `V2` paroles RGBA + `A1` audio master), synchro au frame, transitions, étalonnage global, double export (avec paroles + clean) |
| **Création** | `comp.new`, `layer.newText`, `layer.newShape`, `layer.newSolid`, `layer.newAdjustment`, `add_effect`, scripts JSX (`ec_runtime.py`) | `file.newSequence`, `timeline.place`, `timeline.setTrack`, `timeline.razor`, `timeline.trim`, `timeline.move`, `clip.speedDuration` |
| **Synchro musicale** | Repères exacts issus de `audio/lyrics_timing.json` + écoute à l’oreille ; optionnellement `keys.audioToKeyframes` uniquement si un effet réactif mesuré est voulu | `markers.add` sur chaque section, dernier accent et coupe au noir ; calage exact à la frame (`frame: f0`) |
| **Habillage & Colorimétrie** | Styles de calque, masques, Bézier, lueurs, ombres portées, pré-compositions (`layer.precompose`) | Lumetri Color (`lumetri.applyPreset`, `lumetri.setLook`, `lumetri.applyMatch`), `sequence.colorSettings`, `sequence.applyVideoTransition` |
| **Audio** | Aucun audio exporté sur les rendus intermédiaires (`--audio off`) | Piste master originale sur `A1` (laissée à `0.0 dB` par défaut pour préserver le master original ; `essentialSound.*` ou `sequence.normalizeMixTrack` uniquement sur demande) |

---

## 2. Pipeline d’échange de fichiers & Cohérence technique

### Convention de dossier projet

```text
<project_root>/
├── audio/           # Piste master (WAV/FLAC/MP3) + lyrics_timing.json (source unique éditable)
├── footage/         # Rushes vidéo, photos, logos éventuels
├── renders_vfx/     # Rendus intermédiaires EffectCraft : V01..Vnn.mov (RGB) + L01..Lnn.mov (RGBA)
├── previews/        # Captures PNG (render-frame) + MP4 courts de prévisualisation avec son (ex. refrain, solo)
├── projects/        # Fichiers .ecproj et .fcproj
├── scripts/         # Générateurs spécifiques au clip (important les outils partagés T3 Code)
└── exports/         # Livrables finaux 1080p : *_lyrics.mp4 et *_clean.mp4
```

### Formats d’échange compatibles

- **Paroles & Overlays avec transparence (`V2`)** depuis EffectCraft → FilmCraft :
  - **Recommandé (fichier unique)** : QuickTime **Apple ProRes 4444** (`.mov`), `format: "prores"`, `proresProfile: "4444"`, `channels: "rgba"`, `audio: "off"`.
  - **Alternative sans perte** : Séquence **PNG** ou **OpenEXR** (`channels: "rgba"`), importée dans FilmCraft avec `image_sequence: true`.
  - **Interdit pour l’alpha** : `H264`, `Hevc` et `Av1` ne gèrent pas le canal alpha (`alpha: false`).
- **Scènes visuelles opaques (`V1`)** depuis EffectCraft :
  - `format: "prores"`, `proresProfile: "hq"`, `channels: "rgb"`, `audio: "off"`.
- **Livraison finale depuis FilmCraft** :
  - Web/Diffusion : `format: "h264"` (`.mp4`, preset `"High Quality 1080p HD"`).
  - Master archive : `format: "prores"`. *(Note : sur Linux sans encodeur matériel, `hevc` et `av1` peuvent être indisponibles.)*

### Alignement résolution, cadence (FPS) et colorimétrie

1. **Verrouiller dès le départ** un couple unique `(width, height, fps)` partagé entre EffectCraft (`comp.new`) et FilmCraft (`file.newSequence`), ex. `1920×1080` à `30` ou `24` fps.
2. **Sections alignées à la frame** : calculer chaque borne de section en nombre entier de frames (`f0 / fps .. f1 / fps`) afin que la somme des sections couvre exactement la durée réelle de la piste audio sans dérive ni trou.
3. **Espace colorimétrique** : `workingSpace: "rec709"` en SDR dans les deux logiciels (`file.projectSettings` dans EffectCraft, `sequence.colorSettings` dans FilmCraft ; `autoToneMap: true` si rushes HDR/Log).
4. **Conversion de temps** : EffectCraft travaille en **secondes** (`f64`) ; FilmCraft utilise des **ticks** (`254016000000` ticks = `1` s) et accepte aussi `frame` / `seconds` dans `timeline.place`.

---

## 3. Méthode musicale clé (Calage à l’oreille, Timing éditable, Paroles indépendantes & Instrumentaux)

### A. Calage à l’oreille et mesure exacte de la fin sur le master audio
1. **Toujours mesurer la piste originale à 44,1 kHz (`hop = 441` = 10,000 ms exact)** via `audio_cues.py analyze` (ne jamais utiliser de pas arrondi en 22,05 kHz qui crée une dérive de plusieurs centaines de millisecondes sur 3 minutes).
2. **Vérifier la fin exacte sur le MP3/WAV avant de verrouiller le montage** : repérer le dernier accent fort, le dernier coup de batterie/instrument (ex. coupe au noir) et la fin réelle de la réverbération jusqu’au silence final.
3. **Écouter réellement la piste par tranches** : découper le morceau en tranches qui se chevauchent (ex. 18 s avec 2 s de recouvrement) puis des extraits courts autour des transitions, refrains, chœurs et fins de phrases (`audio_cues.py slice`) et les écouter pour verrouiller le BPM exact et chaque entrée vocale **à l’oreille**.

### B. Fichier unique de timing éditable (`audio/lyrics_timing.json`) et repères incertains
Centraliser **tout le timing des paroles dans un seul fichier JSON éditable à la main** (`audio/lyrics_timing.json`), relu par le générateur EffectCraft :
- `meta` : fichier audio, durée audio/vidéo en ms, `fps`, `bpm`, `first_drum_hit_ms`, `last_accent_ms`, `black_cut_ms`.
- `sections` : bornes `start_ms` / `end_ms` alignées au frame.
- `phrases` :
  - `start_ms`, `end_ms` et **`display_end_ms`** (prolongé de `+250` à `+600 ms` au besoin pour laisser le dernier mot lisible même si le plan ou la section change).
  - `type: "lead"` pour le chant principal et **`type: "echo"` en entrées séparées** pour les chœurs, réponses et ad-libs.
  - `words` (découpage par mots/groupes) **uniquement là où une animation ou un accent visuel en a besoin** ; sinon afficher la phrase entière proprement.
  - **`"uncertain": true` + `"review_note": "..."`** sur tout repère ambigu (chœurs, échos, vocalises superposées, cris brefs) pour permettre à l’utilisateur de les recaler facilement à la main sans toucher au code.

### C. Paroles sur un calque indépendant (`V2` RGBA) & Double export Master / Clean
1. **Aucun bandeau noir permanent** : placer chaque phrase dans l’espace libre du plan (voir [craft-2d-animation §5](../craft-2d-animation/SKILL.md#5-lisibilité-du-texte-et-séparation-diégétique--overlay)), avec ombre portée douce, marges de sécurité et continuité automatique (`isContIn` / `isContOut`) quand `display_end_ms` traverse une coupe de section.
2. **Piste transparente dédiée** : générer les paroles dans des compositions séparées `L01..Lnn` (en omettant les sections purement instrumentales) rendues en **ProRes 4444 RGBA** et posées sur **`V2`** dans FilmCraft.
3. **Conserver le texte du décor sur `V1`** : enseignes, écrans, copies, tableaux restent dans les scènes `V01..Vnn`.
4. **Double export rigoureusement identique** : exporter la version **avec paroles** (`V2` activée), puis désactiver `V2` (`timeline.setTrack {"track": "V2", "enabled": false}`) pour exporter la version **clean** au montage et à l’audio 100 % identiques, puis réactiver `V2` avant la sauvegarde finale du `.fcproj`.

### D. Actions visuelles pendant les passages instrumentaux (Zéro courbe audio générique)
1. **Bannir les béquilles visuelles génériques** : pas de courbes audio, pas de zigzags d’oscilloscope, pas de cercles flottants décoratifs sur les intros, solos ou interludes.
2. **Chorégraphier des actions dessinées sur des accents choisis à l’oreille** : une porte claque, une série de plafonniers s’allume un par un, un décor se déplie en carton/papier 3D sur les riffs, un objet glisse ou un personnage change de pose avec anticipation et maintien.
3. **Tenir les plans entre les accents** : laisser une image claire et stable entre deux temps forts pour que l’action reste lisible.
4. **Appliquer les règles 2D communes** : cadrages variés (large / OTS / profil / gros plan), silhouettes pleines, hiérarchie d’ancres neutres avant transformation (voir [craft-2d-animation](../craft-2d-animation/SKILL.md)).

---

## 4. Workflow étape par étape

### Étape 1 — Analyse audio à l’oreille & Squelette de timing
1. Sonder le master (`audio_cues.py analyze`) à 44,1 kHz pour obtenir la durée exacte, les transitoires 10 ms et le détail de la fin de piste.
2. Extraire des tranches d’écoute (`audio_cues.py slice`) et les écouter pour fixer le BPM exact, les bornes de sections alignées aux frames, les phrases, les échos et la coupe finale.
3. Initialiser et remplir `audio/lyrics_timing.json` en marquant les repères douteux avec `"uncertain": true` + `"review_note"`, puis valider le JSON (`lyrics_overlay.py --validate`).

### Étape 2 — Découpage / Storyboard court (avant tout gros rendu)
1. Rédiger un **plan de montage court** (tableau temps / section / lieu & cadrage / action visuelle dessinée / traitement des paroles).
2. Présenter le découpage (et les choix d’accents pour les passages instrumentaux) à l’utilisateur avant de lancer des rendus complets.

### Étape 3 — Création des scènes (`V01..Vnn`) et paroles (`L01..Lnn`) dans EffectCraft
1. Construire les scènes 2D (`V01..Vnn`) en suivant les règles d’ancres, de parenting neutre et d’empilement de [craft-2d-animation](../craft-2d-animation/SKILL.md) (à l’aide de `ec_runtime.py`).
2. Générer les compositions paroles transparentes (`L01..Lnn`, hors instrumentaux) directement depuis `audio/lyrics_timing.json` via `lyrics_overlay.py`.
3. **Contrôle rapide par captures (`render-frame --max-side 960`)** sur les plans clés (et `--transparent` sur les paroles) pour corriger immédiatement tout chevauchement ou décalage d’ancre avant le rendu vidéo.
4. **Prévisualisations MP4 courtes avec le son** (ex. 1 refrain + 1 solo) : rendre uniquement ces 1–2 sections, muxer avec l’extrait exact du master audio, **les regarder et les écouter** pour recaler au besoin les entrées d’échos, le maintien du dernier mot entre plans et la lisibilité du solo.
5. **Rendu complet basse consommation** vers `./renders_vfx/` via `render_ec_batch.sh` (séquentiel 1 rendu à la fois, ProRes HQ RGB pour `V*`, ProRes 4444 RGBA pour `L*`, reprise automatique via `ffprobe`).
6. **Sauvegarder** `projects/<clip>.ecproj`.

### Étape 4 — Assemblage & Double export dans FilmCraft
1. Assembler la séquence Rec.709 via `assemble_filmcraft.py` (ou via MCP `file.newProject`, `file.newSequence`, `media_import`, `timeline.place`, `markers.add`) :
   - `A1` : master audio original intact (`volumeDb: 0.0`)
   - `V1` : `V01..Vnn.mov` posés à leur frame exacte (`frame: f0`)
   - `V2` : `L01..Lnn.mov` (ProRes 4444 RGBA) posés aux mêmes frames exactes (`audio: false`)
2. Vérifier la séquence (`inspect sequence`) + rendre quelques frames composites `V1+V2` et `V1` seul pour confirmer la découpe alpha et la présence du texte diégétique en version clean.
3. Exporter la **version avec paroles** (`*_lyrics.mp4`), désactiver `V2`, exporter la **version clean** (`*_clean.mp4`), puis réactiver `V2` et sauvegarder `projects/<clip>.fcproj`.

### Étape 5 — Audit final obligatoire (Avec son + Sans son)
1. **Contrôle AVEC le son** sur l’export `*_lyrics.mp4` : vérifier les fins de phrases, les coupes de refrains, l’entrée des échos, la coupe au noir exacte et la fin propre de la piste audio originale.
2. **Contrôle SANS le son (muet)** sur les passages instrumentaux (solo, interlude) depuis `*_clean.mp4` : vérifier que l’objectif du personnage et la progression visuelle sont 100 % compréhensibles sans audio, sans aucune courbe audio résiduelle et avec le texte du décor intact.
3. Présenter les livrables et lister explicitement les repères marqués `"uncertain": true` dans `lyrics_timing.json`.

---

## 5. Outils partagés T3 Code & Dépendances

Les outils réutilisables se trouvent dans **`~/.t3/shared/craft-video/`** :

| Outil | Chemin | Usage clip musical |
| :--- | :--- | :--- |
| **Analyse & découpe audio 44,1 kHz** | `~/.t3/shared/craft-video/audio_cues.py` | Durée exacte, transitoires 10 ms sans dérive, inspection de la fin, tranches d’écoute à l’oreille, squelette `lyrics_timing.json` |
| **Validateur & générateur paroles RGBA** | `~/.t3/shared/craft-video/lyrics_overlay.py` | Validation de `lyrics_timing.json`, liste des repères `"uncertain": true`, génération des comps transparentes `L01..Lnn` sans bandeau noir |
| **Runtime JSX EffectCraft** | `~/.t3/shared/craft-video/ec_runtime.py` | `JsxBuilder`, `makeCamNull`, `cam_focus`, formes vectorielles/Bézier, lueurs, ombres, keyframes, runner CLI |
| **Rendu batch séquentiel basse charge** | `~/.t3/shared/craft-video/render_ec_batch.sh` | Rendu `V*` (ProRes HQ RGB) + `L*` (ProRes 4444 RGBA) 1 par 1, reprise `ffprobe`, bridage RAM/CPU |
| **Assemblage FilmCraft & double export** | `~/.t3/shared/craft-video/assemble_filmcraft.py` | Montage `V1` + `V2` + `A1`, marqueurs de sections/fin, double export synchronisé `lyrics` + `clean` |

### Dépendances nécessaires
- **Python 3.9+** (bibliothèque standard uniquement — pas de `numpy`/`librosa` requis)
- **`ffmpeg` et `ffprobe`**
- **EffectCraft CLI** (`effectcraft-cli` ou Flatpak `ai.storyteller.effectcraft`)
- **FilmCraft CLI** (`filmcraft-cli` ou Flatpak `ai.storyteller.filmcraft`)
- Optionnels Linux pour le mode basse charge : `nice`, `ionice`, `taskset`

### Commandes d’exemple

```bash
# 1. Inspecter la piste originale à 44,1 kHz (durée exacte + fin de piste) et découper pour écoute à l’oreille
python3 ~/.t3/shared/craft-video/audio_cues.py analyze ./audio/track.mp3 --bpm 122 --first-beat 0.61
python3 ~/.t3/shared/craft-video/audio_cues.py slice ./audio/track.mp3 --out-dir ./previews/audio_slices --segment-sec 18 --overlap-sec 2

# 2. Valider audio/lyrics_timing.json et afficher tous les repères incertains
python3 ~/.t3/shared/craft-video/lyrics_overlay.py --timing ./audio/lyrics_timing.json --validate

# 3. Vérifier le plan de rendu EffectCraft séquentiel (RGB + RGBA) en --dry-run
~/.t3/shared/craft-video/render_ec_batch.sh \
  --project ./projects/clip.ecproj --out-dir ./renders_vfx \
  --rgb V01_Intro,V02_Verse,V03_Chorus --rgba L01_Intro,L02_Verse,L03_Chorus \
  --threads 2 --cores 0-3 --dry-run

# 4. Vérifier l’assemblage FilmCraft et le double export (avec paroles + clean) en --dry-run
python3 ~/.t3/shared/craft-video/assemble_filmcraft.py \
  --out-fcproj ./projects/clip.fcproj \
  --timing ./audio/lyrics_timing.json \
  --renders-dir ./renders_vfx \
  --export-master ./exports/clip_1080p_lyrics.mp4 \
  --export-clean ./exports/clip_1080p_clean.mp4 \
  --dry-run
```

---

## 6. Garde-fous obligatoires

- **Sauvegarde explicite en headless** : ni FilmCraft ni EffectCraft ne sauvegardent automatiquement les modifications MCP/CLI sans appel explicite (`--save` / `--save-as`, `file.save`, `save_project`).
- **Zéro édition concurrente GUI / Headless** : utiliser `--bridge` si le projet est ouvert dans l’interface graphique, sinon fermer la GUI avant toute opération headless.
- **Ménager RAM & CPU sur machines légères (8 Go RAM)** : ne jamais paralléliser plusieurs rendus ProRes 4444 RGBA ; utiliser `render_ec_batch.sh` (séquentiel 1 par 1, `--threads 2`, `nice -n 15 ionice -c 3`, sans `--gpu` sur GPU intégré à mémoire partagée).
- **Annulation & Atomicité** : préférer `batch` (`atomic: true`) dans EffectCraft et `edit.undo` / `history` dans FilmCraft ; en cas de doute sur une commande moteur, appeler `describe_command` (EffectCraft) ou `command_list` (FilmCraft) au lieu de deviner.
