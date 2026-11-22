---
name: craft-2d-animation
description: >-
  Direct and build crisp 2D animated intros, product demos, and short narrative
  scenes in EffectCraft (and optional FilmCraft assembly), with or without music.
  Covers shot framing and cinematography, solid-silhouette character design, pose
  changes with anticipation and holds, character/camera anchor and parenting rules,
  layer stacking order, text legibility (diegetic vs independent RGBA overlay),
  and low-resource rendering via shared T3 Code tools. Use whenever creating or
  refining 2D animated videos, UI demos, explainers, channel intros, or short
  animated scenes in EffectCraft/FilmCraft.
---

# Craft 2D Animation (`EffectCraft` + `FilmCraft`)

Méthode générale et réutilisable pour concevoir, animer et assembler des **intros, démos produit, scènes courtes ou courts-métrages 2D** dans EffectCraft (avec montage/export optionnel dans FilmCraft), **avec ou sans piste musicale**.

> Référence CLI/MCP et permissions Flatpak partagées : [../craft-music-video/references/mcp-and-commands.md](../craft-music-video/references/mcp-and-commands.md).

---

## 1. Direction visuelle et lisibilité de scène

1. **Lieux identifiables par la couleur** : limiter une courte scène à **2 ou 3 lieux maximum**, chacun doté d’une lumière dominante et d’une palette dédiée (ex. couloir chaud/nuit, poste de travail éclairé par un écran, salle claire avec une seule couleur d’accent réservée aux erreurs ou alertes).
2. **Silhouettes pleines plutôt que contours creux** : construire les personnages et décors en formes géométriques **remplies** (courbes de Bézier ou rectangles arrondis) avec des visages minimalistes (yeux, sourcils, bouche simples) et un léger liseré de contre-jour (`rim light`) côté source lumineuse.
3. **Contraste de silhouettes** : distinguer chaque personnage dès la miniature (ex. silhouette arrondie qui se tasse vs silhouette droite aux épaules carrées et gestes secs).
4. **Décors surdimensionnés pour les mouvements caméra** : dessiner les fonds/murs plus larges que le cadre (`2200–2400 px` pour un zoom/shake en `1920×1080`, ou `3600+ px` pour un travelling panoramique) afin d’éviter toute bordure noire de 10–20 px sur les bords du cadre.

---

## 2. Cadrages et grammaire visuelle

Varier les valeurs de plan pour raconter l’action sans texte superflu :

| Valeur de plan | Rôle narratif | Bonnes pratiques techniques |
| :--- | :--- | :--- |
| **Plan large (Establishing)** | Présenter le lieu, l’éclairage et la position relative des éléments | Garder un repère spatial fixe (bureau, écran, panneau, porte) lors des retours dans le même lieu |
| **Par-dessus l’épaule (OTS)** | Montrer l’objectif du personnage et son point de vue sur une interface ou un objet | Réutiliser **exactement le même cadrage OTS** entre la première tentative et la réussite finale pour créer un rappel visuel immédiat |
| **Plan moyen / Profil** | Suivre la posture, les déplacements et l’évolution physique d’une scène | Idéal pour montrer un tassement progressif, un recul sur chaise ou un geste ample |
| **Gros plan (Close-up)** | Isoler une intention, un détail d’interface, une main sur une touche, un regard ou un gag | Garder les mouvements courts et lisibles ; profiter du gros plan pour dégager des zones négatives propres |

### Calcul de cadrage caméra (`cam_focus`)
Avec un nul caméra d’ancre `[0, 0]`, centrer un point du monde `(tx, ty)` au milieu d’un cadre `W × H` à l’échelle `sc %` obéit exactement à :
`pos = [W / 2 - (sc / 100) * tx, H / 2 - (sc / 100) * ty]`
(disponible directement via `cam_focus(tx, ty, scale_pct, width, height)` dans [ec_runtime.py](~/.t3/shared/craft-video/ec_runtime.py)).

---

## 3. Changements de pose, poids et rythme visuel

1. **Anticipation → Action → Rebond / Maintien** :
   - Ne jamais passer linéairement d’une pose A à une pose B.
   - Ajouter une **petite anticipation** de sens opposé avant l’action (ex. doigt qui se lève et hésite avant de frapper une touche, porte qui s’ouvre légèrement avant de claquer, corps qui prend appui avant de reculer).
   - Terminer par un léger dépassement (`overshoot`) ou un temps d’arrêt lisible (`hold`) pour donner du poids (ex. personnage qui recule d’un pas et marque une pause pour admirer son travail).
2. **Paliers de posture progressifs** : lors d’une attente ou d’une montée de tension, faire évoluer la posture par paliers nets entre deux plans (inclinaison du torse, baisse de la tête, relâchement des bras) plutôt que par un flottement permanent.
3. **Tenir les plans entre deux actions** : laisser respirer la composition entre les accents (clignements d’yeux, micro-zoom lent, curseur qui clignote) plutôt que d’agiter tous les calques en continu.
4. **Test muet obligatoire** : visionner toute scène d’action, d’intro ou de démo **sans le son** (ou via 3–5 captures clés `render-frame`). L’objectif du personnage et la progression de la scène doivent rester 100 % compréhensibles à l’image seule.

---

## 4. Ancres des personnages, des caméras et ordre d’empilement (Pièges EffectCraft)

Ces règles évitent les bugs de décalage, de membres détachés ou d’éléments cachés dans EffectCraft (comportement compatible After Effects) :

### A. Nuls et caméras
- `comp.layers.addNull()` crée par défaut une ancre à `[50, 50]` et une position à `[960, 540]`. **Toujours forcer `anchorPoint.setValue([0, 0])`** avant de positionner ou parenter le nul (c’est ce que fait `makeCamNull` dans `ec_runtime.py`).
- **Toujours assigner `child.parent = parent` AVANT `child.position.setValue(...)`**, afin que les coordonnées de `child` soient interprétées directement dans le repère local du parent.

### B. Règle absolue sur le parenting et les transformations
- **Attacher TOUS les enfants pendant que le parent est en pose neutre** (`rotation = 0°`, `scale = [100, 100]`).
- **N’appliquer les rotations initiales, zooms caméra ou keyframes du parent qu’APRÈS** la création complète de toute la hiérarchie enfant.
- *Pourquoi* : modifier `parent.rotation` ou `parent.scale` avant d’assigner `child.parent = parent` déclenche une compensation inverse AE-style qui projette la tête/les bras hors du corps ou rétrécit tout un décor dans un coin du cadre.

### C. Hiérarchie d’ancres d’un personnage 2D articulé
- **Personnage assis** : `Root` aux **hanches** (`hip_pos`) → `Chair`, `Legs`, `TorsoNull` (pivot taille `[0, 0]`) → `BackUpperArm` (épaule) → `BackForeArm` (coude) → `TorsoBody` → `Head` (base du cou) → `UpperArm` → `ForeArm`.
- **Personnage debout** : `Root` au **sol entre les pieds** (`foot_pos`) pour garder les chaussures plantées au sol lors d’un zoom ou d’un pas en arrière → `LegBack` / `LegFront` (pivot hanches) + `TorsoPivot` (pivot hanches) → `Arms`, `Blazer/Body`, `Head`.
- **Raccord cou / col** : toujours ajouter une forme pleine de **col / cou chevauchant le haut du torse et le bas de la tête** afin qu’une forte inclinaison (`25°–35°`) n’ouvre jamais un jour entre le menton et les épaules.

### D. Ordre d’empilement (Stacking Order)
- **À l’intérieur d’un même calque de forme (`ADBE Root Vectors Group`)** : le **premier** groupe ajouté se dessine **AU-DESSUS**, le dernier **EN DESSOUS** (ordre **avant → arrière**).
- **Entre calques distincts d’une composition** : chaque nouveau calque est inséré à l’index `1` (**AU-DESSUS**). Construire les calques dans l’ordre **arrière → avant** (fond → lueur → décor → personnage → avant-plan).

---

## 5. Lisibilité du texte et séparation diégétique / overlay

1. **Aucun bandeau noir permanent** : placer les titres, sous-titres ou légendes dans l’**espace négatif libre** de chaque plan (au-dessus d’un écran, dans un coin sombre du mur, sous une ligne d’horizon), sans jamais chevaucher un visage, une bordure d’écran ou un panneau du décor.
2. **Contraste et marges de sécurité** :
   - Appliquer une ombre portée douce (`ADBE Drop Shadow`, opacité `190–230`, distance `4–6 px`, flou `14–18 px`) pour garantir la lecture sur fond clair comme foncé.
   - Respecter des marges horizontales de sécurité (`>= 70 px` en `1920×1080`) et un temps de maintien lisible (`>= 0.35 s` après la fin de l’action ou du dernier mot, y compris à travers une coupe de plan).
3. **Séparation stricte Texte diégétique (`V1`) vs Texte superposé (`V2`)** :
   - **Texte intégré au décor (`V1`)** : enseignes, interfaces écran, feuilles, tableaux, touches de clavier. Il fait partie du monde animé et reste présent sur tous les exports.
   - **Texte superposé (`V2`, ProRes 4444 RGBA)** : titres, cartons, sous-titres, paroles ou annotations UI. Le placer dans des compositions transparentes séparées permet d’exporter en un clic une version **avec titres** et une version **clean** au montage rigoureusement identique.

---

## 6. Vérification visuelle et rendu économe en ressources

1. **Contrôle par images clés avant tout rendu vidéo** : utiliser `effectcraft-cli render-frame --max-side 960` sur 1 à 2 instants clés par plan (et `--transparent` pour les overlays `V2`) afin de vérifier cadrages, raccords d’articulations et lisibilité du texte en quelques secondes.
2. **Rendu séquentiel sûr (machines 8 Go RAM / CPU modeste)** :
   - Rendre **1 seule composition à la fois** (jamais de rendus ProRes 4444 RGBA en parallèle sur 8 Go de RAM).
   - Brider les threads (`RAYON_NUM_THREADS=2`, `OMP_NUM_THREADS=2`), lancer en priorité basse (`nice -n 15 ionice -c 3`), éviter `--gpu` si la VRAM est partagée avec la RAM système, et laisser 2 s entre deux rendus pour libérer la mémoire.

---

## 7. Outils partagés T3 Code & Dépendances

Les scripts réutilisables se trouvent dans **`~/.t3/shared/craft-video/`** :

| Outil | Chemin | Usage en animation 2D |
| :--- | :--- | :--- |
| **Runtime JSX EffectCraft** | `~/.t3/shared/craft-video/ec_runtime.py` | Importer `JsxBuilder`, `cam_focus`, `hex_to_rgba`, `run_effectcraft_script` pour générer proprement un `.ecproj` (ancre `[0,0]`, Bézier, glows, keyframes lissées/hold) |
| **Rendu batch séquentiel** | `~/.t3/shared/craft-video/render_ec_batch.sh` | Rendre les scènes `V*` (ProRes HQ RGB) et overlays `L*`/`T*` (ProRes 4444 RGBA) en basse charge avec reprise automatique via `ffprobe` |
| **Assemblage & Export FilmCraft** | `~/.t3/shared/craft-video/assemble_filmcraft.py` | Assembler `V1` (+ `V2` alpha et `A1` audio optionnels) en Rec.709 dans un `.fcproj` et exporter Master + Clean |

### Dépendances nécessaires
- **Python 3.9+** (bibliothèque standard uniquement)
- **`ffmpeg` et `ffprobe`**
- **EffectCraft CLI** (`effectcraft-cli` ou Flatpak `ai.storyteller.effectcraft` avec accès `--filesystem`)
- **FilmCraft CLI** (`filmcraft-cli` ou Flatpak `ai.storyteller.filmcraft`) pour l’assemblage/export multi-pistes
- Optionnels Linux : `nice`, `ionice`, `taskset`

### Commandes d’exemple

```bash
# Vérifier les dépendances disponibles (aucun rendu)
python3 ~/.t3/shared/craft-video/ec_runtime.py --check-env

# Prévisualiser le plan de rendu séquentiel basse charge (scène + titres alpha)
~/.t3/shared/craft-video/render_ec_batch.sh \
  --project ./projects/demo_2d.ecproj \
  --out-dir ./renders_vfx \
  --rgb V01_Intro,V02_Demo \
  --rgba T01_Intro,T02_Demo \
  --threads 2 --cores 0-3 --dry-run

# Prévisualiser l’assemblage FilmCraft sans musique (intro/démo muette, Master + Clean)
python3 ~/.t3/shared/craft-video/assemble_filmcraft.py \
  --out-fcproj ./projects/demo_2d.fcproj \
  --v1-clips ./renders_vfx/V01_Intro.mov,./renders_vfx/V02_Demo.mov \
  --v2-clips ./renders_vfx/T01_Intro.mov,./renders_vfx/T02_Demo.mov \
  --export-master ./exports/demo_2d_titles.mp4 \
  --export-clean ./exports/demo_2d_clean.mp4 \
  --dry-run
```
