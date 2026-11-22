# Craft Video Kit (`EffectCraft` + `FilmCraft`)

Skills et outils partagés réutilisables pour produire des **animations 2D** (intros, démos, scènes courtes, avec ou sans musique) et des **clips musicaux synchronisés** avec **EffectCraft** et **FilmCraft**.

## Structure

- `skills/craft-2d-animation/` — Skill général d’animation 2D (`SKILL.md`)
- `skills/craft-music-video/` — Skill de clips musicaux (`SKILL.md` + `references/mcp-and-commands.md`)
- `tools/craft-video/` — Outils CLI/Python partagés (`ec_runtime.py`, `audio_cues.py`, `lyrics_overlay.py`, `render_ec_batch.sh`, `assemble_filmcraft.py`)

## Installation rapide

```bash
# 1. Copier les outils partagés dans T3 Code
mkdir -p ~/.t3/shared/craft-video
cp -r tools/craft-video/* ~/.t3/shared/craft-video/

# 2. Copier les skills dans un projet (.agents/skills/)
mkdir -p /chemin/vers/projet/.agents/skills
cp -r skills/craft-2d-animation skills/craft-music-video /chemin/vers/projet/.agents/skills/
```
