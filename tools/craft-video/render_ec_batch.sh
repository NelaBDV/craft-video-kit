#!/usr/bin/env bash
# render_ec_batch.sh — Low-resource-safe sequential batch renderer for EffectCraft (.ecproj)
#
# Designed to avoid OOM/freezes on 8 GB RAM / modest CPU machines:
#   - Strictly sequential by default (1 render process at a time, nice -n 15, ionice -c 3)
#   - Caps Rayon/OpenMP threads (--threads 2) and optional CPU affinity (--cores 0-3)
#   - Resumes cleanly: skips .mov files newer than .ecproj that pass ffprobe validation
#   - Auto-detects native `effectcraft-cli` or Flatpak `ai.storyteller.effectcraft`
#
# Dependencies: bash, effectcraft-cli (native or Flatpak), ffprobe (ffmpeg), optional taskset/ionice.

set -euo pipefail

PROJECT=""
OUT_DIR=""
RGB_COMPS=""
RGBA_COMPS=""
THREADS="2"
CORES=""
PAUSE_SEC="2"
USE_GPU="0"
FORCE="0"
DRY_RUN="0"

usage() {
  cat <<'EOF'
Usage: render_ec_batch.sh --project FILE.ecproj --out-dir DIR [options]

Options:
  --project PATH        EffectCraft project (.ecproj) [required]
  --out-dir DIR         Output directory for .mov renders [required]
  --rgb LIST            Comma-separated opaque comps (ProRes HQ RGB)
  --rgba LIST           Comma-separated alpha overlay comps (ProRes 4444 RGBA)
  --threads N           RAYON_NUM_THREADS / OMP_NUM_THREADS cap (default: 2)
  --cores SPEC          Optional CPU affinity for taskset, e.g. '0-3' (default: unset)
  --pause SEC           Cooldown seconds between renders to reclaim RAM (default: 2)
  --gpu                 Enable EffectCraft --gpu renderer (off by default to save unified RAM)
  --force               Re-render even if valid up-to-date .mov already exists
  --dry-run             Print planned commands without rendering
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)   PROJECT="$2"; shift 2 ;;
    --out-dir)   OUT_DIR="$2"; shift 2 ;;
    --rgb)       RGB_COMPS="$2"; shift 2 ;;
    --rgba)      RGBA_COMPS="$2"; shift 2 ;;
    --threads)   THREADS="$2"; shift 2 ;;
    --cores)     CORES="$2"; shift 2 ;;
    --pause)     PAUSE_SEC="$2"; shift 2 ;;
    --gpu)       USE_GPU="1"; shift ;;
    --force)     FORCE="1"; shift ;;
    --dry-run)   DRY_RUN="1"; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PROJECT" || -z "$OUT_DIR" ]]; then
  echo "Error: --project and --out-dir are required." >&2
  usage >&2
  exit 2
fi

if [[ -z "$RGB_COMPS" && -z "$RGBA_COMPS" ]]; then
  echo "Error: specify at least one of --rgb or --rgba." >&2
  exit 2
fi

PROJECT="$(realpath -m "$PROJECT")"
OUT_DIR="$(realpath -m "$OUT_DIR")"
PROJ_DIR="$(dirname "$PROJECT")"
mkdir -p "$OUT_DIR"

build_ec_cmd() {
  local -n _arr=$1
  _arr=()
  if command -v nice >/dev/null 2>&1; then
    _arr+=(nice -n 15)
  fi
  if command -v ionice >/dev/null 2>&1; then
    _arr+=(ionice -c 3)
  fi
  if [[ -n "$CORES" ]] && command -v taskset >/dev/null 2>&1; then
    _arr+=(taskset -c "$CORES")
  fi
  if command -v effectcraft-cli >/dev/null 2>&1; then
    _arr+=(effectcraft-cli)
  else
    _arr+=(flatpak run "--filesystem=$PROJ_DIR" "--filesystem=$OUT_DIR" --command=effectcraft-cli ai.storyteller.effectcraft)
  fi
  if [[ "$USE_GPU" == "1" ]]; then
    _arr+=(--gpu)
  fi
}

is_valid_mov() {
  local mov="$1"
  [[ -f "$mov" && -f "$PROJECT" && "$mov" -nt "$PROJECT" ]] || return 1
  ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$mov" >/dev/null 2>&1
}

render_one() {
  local mode="$1"
  local comp="$2"
  local out_mov="$OUT_DIR/${comp}.mov"

  if [[ "$FORCE" != "1" ]] && is_valid_mov "$out_mov"; then
    echo "  [SKIP valid] $comp -> $out_mov"
    return 0
  fi

  local cmd=()
  build_ec_cmd cmd
  if [[ "$mode" == "rgb" ]]; then
    cmd+=(--project "$PROJECT" render --comp "$comp" --out "$out_mov" --format prores --prores hq --channels rgb --audio off)
  else
    cmd+=(--project "$PROJECT" render --comp "$comp" --out "$out_mov" --format prores --prores 4444 --channels rgba --audio off)
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  [DRY-RUN $mode] RAYON_NUM_THREADS=$THREADS OMP_NUM_THREADS=$THREADS ${cmd[*]}"
    return 0
  fi

  rm -f "$out_mov"
  echo "  [RENDER ${mode^^}] $comp -> $out_mov"
  RAYON_NUM_THREADS="$THREADS" OMP_NUM_THREADS="$THREADS" "${cmd[@]}"
  if [[ "$PAUSE_SEC" != "0" ]]; then
    sleep "$PAUSE_SEC"
  fi
}

if [[ -n "$RGB_COMPS" ]]; then
  echo "=== Opaque RGB comps (ProRes HQ, sequential) ==="
  IFS=',' read -ra _rgb_list <<< "$RGB_COMPS"
  for comp in "${_rgb_list[@]}"; do
    comp="${comp//[[:space:]]/}"
    [[ -n "$comp" ]] && render_one rgb "$comp"
  done
fi

if [[ -n "$RGBA_COMPS" ]]; then
  echo "=== Alpha RGBA overlay comps (ProRes 4444, sequential) ==="
  IFS=',' read -ra _rgba_list <<< "$RGBA_COMPS"
  for comp in "${_rgba_list[@]}"; do
    comp="${comp//[[:space:]]/}"
    [[ -n "$comp" ]] && render_one rgba "$comp"
  done
fi

echo "BATCH_RENDER_COMPLETE"
