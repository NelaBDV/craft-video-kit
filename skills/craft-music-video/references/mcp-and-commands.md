# Référence MCP & Commandes Vérifiées — FilmCraft & EffectCraft

Référence technique vérifiée sur cette machine (Flatpak `ai.storyteller.filmcraft` v0.20.1 et `ai.storyteller.effectcraft` v0.24.1) et d'après `craft.wiki`.

---

## 1. Configuration des serveurs MCP

### Linux (Flatpak — installation détectée sur ce poste)

Sur ce système, les binaires ne sont pas sur `$PATH` mais exécutés via Flatpak :
- FilmCraft CLI : `flatpak run --command=filmcraft-cli ai.storyteller.filmcraft`
- EffectCraft CLI : `flatpak run --command=effectcraft-cli ai.storyteller.effectcraft`

#### Permission Flatpak indispensable pour EffectCraft
Par défaut, `ai.storyteller.effectcraft` ne voit que `xdg-documents`, `xdg-pictures` et `xdg-videos`. Pour qu'il puisse lire/écrire dans un dossier de projet quelconque (comme `~/.t3/projects/...`) :

```bash
flatpak override --user --filesystem=home ai.storyteller.effectcraft
```

*(Alternative plus stricte : `--filesystem=~/.t3/projects`.)*

---

### Mode Headless (recommandé pour automatisation sans fenêtre ouverte)

#### Antigravity / Clients JSON (`~/.gemini/config/mcp_config.json` ou Claude Desktop)
```json
{
  "mcpServers": {
    "filmcraft": {
      "command": "flatpak",
      "args": [
        "run",
        "--command=filmcraft-cli",
        "ai.storyteller.filmcraft",
        "mcp"
      ]
    },
    "effectcraft": {
      "command": "flatpak",
      "args": [
        "run",
        "--command=effectcraft-cli",
        "ai.storyteller.effectcraft",
        "mcp",
        "--autosave"
      ]
    }
  }
}
```
*Options utiles :*
- FilmCraft : ajouter `"--project", "/chemin/projet.fcproj"` ou `"--demo"` dans `args` (ou ouvrir ensuite via `command_run` `file.open`).
- EffectCraft : `"--autosave"` préserve les modifications non enregistrées en cas de coupure, mais appeler tout de même `save_project`. Possibilité de restreindre les dossiers via `"--automation-read-root", "<dir>"` et `"--automation-write-root", "<dir>"`.

#### Claude Code
```bash
claude mcp add --scope user filmcraft -- flatpak run --command=filmcraft-cli ai.storyteller.filmcraft mcp
claude mcp add --scope user effectcraft -- flatpak run --command=effectcraft-cli ai.storyteller.effectcraft mcp --autosave
```

#### Codex (`~/.codex/config.toml` ou CLI)
```bash
codex mcp add filmcraft -- flatpak run --command=filmcraft-cli ai.storyteller.filmcraft mcp
codex mcp add effectcraft -- flatpak run --command=effectcraft-cli ai.storyteller.effectcraft mcp --autosave
```

*(Si installés via `.deb`/`.rpm` natifs hors Flatpak, remplacer `flatpak run --command=<app>-cli ai.storyteller.<app>` par `/usr/bin/filmcraft-cli` et `/usr/bin/effectcraft-cli`.)*

---

### Mode Bridge (piloter la GUI ouverte en temps réel)

#### FilmCraft (nécessite `FILMCRAFT_CONTROL_TOKEN` de 64 caractères hex)
1. Générer un jeton de session et lancer la GUI :
```bash
export FILMCRAFT_CONTROL_TOKEN=$(openssl rand -hex 32)
flatpak run ai.storyteller.filmcraft --control 9876
```
2. Connecter le MCP depuis un environnement partageant la même variable `FILMCRAFT_CONTROL_TOKEN` :
```bash
flatpak run --command=filmcraft-cli ai.storyteller.filmcraft mcp --bridge 127.0.0.1:9876
```

#### EffectCraft
1. Lancer la GUI avec port de contrôle :
```bash
flatpak run ai.storyteller.effectcraft --control 9877
```
2. Connecter le MCP en bridge :
```bash
flatpak run --command=effectcraft-cli ai.storyteller.effectcraft mcp --bridge 9877
```

---

## 2. Outils MCP disponibles (vérifiés par `tools/list`)

### FilmCraft MCP (17 outils)
- **Inspection & Découverte** : `command_list(enabled_only, filter)`, `doc_inspect()`, `project_inspect()`, `sequence_inspect()`
- **Exécution** : `command_run(id*, params)`, `command_batch(steps*, stop_on_error)`
- **Médias & Aperçu** : `media_import(paths*, bin, image_sequence)`, `render_frame(seconds, max_side)`, `render_preview(seconds, max_side)`
- **UI (mode `--bridge` uniquement)** : `ui_inspect()`, `ui_elements(prefix)`, `ui_screenshot(panel, max_side)`, `ui_click(...)`, `ui_drag(...)`, `ui_type(text*)`, `ui_key(key*)`, `ui_control(method*, params)`

### EffectCraft MCP (27 outils)
- **Découverte** : `list_commands(filter, enabled_only, compact, schemas)`, `describe_command(id, command)`, `list_effects(filter, compact)`, `list_fonts(query, variable, rescan)`
- **Inspection** : `get_state()`, `get_project()`, `doc_inspect()`, `get_comp(comp)`, `get_layer(layer*, comp, depth, flat, time)`, `get_property(layer*, path*, comp, time)`
- **Édition & Scripts** : `execute_command(command, id, params)`, `command_run(id*, params)`, `batch(steps*, atomic, label)`, `command_batch(steps*, stop_on_error)`, `set_property(...)`, `add_keyframe(...)`, `add_effect(layer*, effect*, comp, values)`, `run_script(code*, name)`, `script_ui(...)`
- **Projet & Historique** : `open_project(path, demo, new)`, `save_project(path)`, `undo(steps)`, `redo(steps)`, `history(goto)`
- **Aperçu** : `render_frame(comp, time, max_side, path, inline, transparent)`, `render_preview(comp, time, max_side, transparent)`

---

## 3. Commandes moteur clés (à passer à `command_run` / `execute_command`)

### EffectCraft (`execute_command` / `batch`)
| Catégorie | ID commande | Paramètres principaux |
| :--- | :--- | :--- |
| Projet | `file.newProject` / `file.open` / `file.save` / `file.saveAs` | `{path}` |
| Config projet | `file.projectSettings` | `{bitDepth?: 8\|16\|32, workingSpace?: "rec709"\|..., renderer?: "gpu"\|"software"}` |
| Import | `file.import` | `{paths: [str], sequence?: bool, frameRate?: fps, importAs?: "footage"\|"composition"}` |
| Composition | `comp.new` / `comp.settings` | `{name?, width?, height?, frameRate?, duration? (s), background?}` |
| Calques | `layer.newText` / `layer.newSolid` / `layer.newShape` / `layer.newNull` / `layer.newAdjustment` | `{text?, size?, fill?, font?}`, `{color?, width?, height?}`, `{kind?: "rect"\|"ellipse"\|...}` |
| Footage → Comp | `layer.addItem` | `{item: id\|name, time? (s), in? (s), out? (s), index?, position?}` |
| Audio → Keyframes | `keys.audioToKeyframes` | `{comp?}` (crée le nul `Audio Amplitude`) |
| Marqueurs | `comp.addMarker` / `markers.set` | `{time?, comment?}` |
| Effets | `effect.apply` / `effect.list` | `{effect: id\|name, layers?}` |
| File de rendu | `renderQueue.add` | `{comp?, format?, output?, channels?: "rgb"\|"rgba"\|"alpha", proresProfile?, quality?: "best"\|"draft", resolution?: "full"\|"half"\|"third"\|"quarter", timeSpan?: "workArea"\|"comp"\|"custom", start?, end?}` |
| Options sortie | `renderQueue.setOutputModule` | `{item?, module?, format?, channels?: "rgb"\|"rgba"\|"alpha", color?: "straight"\|"premultiplied", proresProfile?: "proxy"\|"lt"\|"standard"\|"hq"\|"4444"\|"4444xq", audio?: "auto"\|"on"\|"off"}` |
| Lancer rendu | `renderQueue.render` | `{wait?: true}` |
| Historique | `edit.undo` / `edit.redo` | *(ou outils MCP `undo`, `redo`, `history`)* |

### FilmCraft (`command_run` / `command_batch`)
> Rappel : `254016000000` ticks = 1 seconde. Beaucoup de commandes acceptent `{seconds}`, `{frame}` ou `{timecode}`.

| Catégorie | ID commande | Paramètres principaux |
| :--- | :--- | :--- |
| Projet | `file.newProject` / `file.open` / `file.save` / `file.saveAs` | `{name}` / `{path}` |
| Séquence | `file.newSequence` / `sequence.settings` | `{name, width, height, fps, sampleRate, video, audio}` / `{workingSpace?: "rec709"\|..., autoToneMap?: bool}` |
| Couleur seq | `sequence.colorSettings` | `{workingSpace?: "rec709"\|"rec2100-pq"\|"rec2100-hlg", wideGamut?: bool, autoToneMap?: bool}` |
| Montage | `timeline.place` | `{item\|items, track?: "V1"\|"A1"\|"new", audioTrack?: "A1"\|"new", time\|seconds\|frame, sourceIn?, duration?, video?, audio?, insert?}` |
| Découpe/Trim | `timeline.razor` / `timeline.trim` / `timeline.move` / `edit.rippleDelete` | `{time\|seconds, track?, clip?}` / `{clip, edge: "in"\|"out", mode: "regular"\|"ripple", delta\|deltaFrames}` |
| Vitesse/Remix | `clip.speedDuration` / `clip.remix` | `{clips?, speed, maintainPitch?, interpolation?}` / `{clip?, seconds?}` |
| Marqueurs | `playhead.set` + `markers.add` | `{seconds\|frame\|timecode}` + `{target?: "program"\|"source", time?, name?, comment?, color?}` |
| Transitions | `sequence.applyVideoTransition` / `sequence.applyAudioTransition` | `{clip?, effect: "Cross Dissolve"\|..., frames?, edge?: "in"\|"out"}` |
| Étalonnage | `lumetri.presets` / `lumetri.applyPreset` / `lumetri.setLook` / `lumetri.applyMatch` | `{name, clips?}` / `{clip?, lut, path?}` |
| Audio | `essentialSound.setType` / `essentialSound.autoMatch` / `sequence.normalizeMixTrack` | `{clips?, type: "dialogue"\|"music"\|"sfx"\|"ambience"}` / `{db: 0}` |
| Export | `file.exportMedia` / `export.quick` / `export.presets.list` | `{path, preset?, format?: "h264"\|"prores"\|"dnxhr"\|"png"\|..., range?: "entire"\|"inOut"\|"workArea"\|"custom", startSeconds?, endSeconds?, wait: true}` |
| Historique | `edit.undo` / `edit.redo` / `history.list` | `{}` |
