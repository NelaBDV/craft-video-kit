#!/usr/bin/env python3
"""
lyrics_overlay.py — Generate transparent RGBA lyric overlay compositions in EffectCraft
directly from a single editable `lyrics_timing.json` file, and validate timing files.

Key features:
  - ZERO permanent black lyric banner: places each phrase in the open negative space
    of the shot with crisp configurable drop shadow (`ADBE Drop Shadow`).
  - Independent RGBA compositions (`L01_...`, skipping purely instrumental sections)
    designed to render as ProRes 4444 RGBA onto track V2 in FilmCraft so a Clean
    version (keeping diegetic set text on V1) can be exported by disabling V2.
  - Seamless cross-section hold continuity when `display_end_ms` crosses a section cut.
  - Separate choir/ad-lib echo entries (`type: "echo"`), optional word-level highlights
    (`words`), and `--validate` report listing every `"uncertain": true` cue for review.

Dependencies: Python 3.9+ (standard library only) + `ec_runtime.py` in the same folder.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ec_runtime import (
    DEFAULT_FONT,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    JsxBuilder,
    frame_aligned_sections,
    hex_to_rgb,
)


DEFAULT_PALETTE: Dict[str, List[float]] = {
    "cream":         [0.973, 0.957, 0.918],
    "white":         [0.985, 0.985, 0.990],
    "amber":         [1.000, 0.745, 0.235],
    "amber_soft":    [0.980, 0.835, 0.490],
    "violet_bright": [0.784, 0.608, 1.000],
    "cyan":          [0.420, 0.880, 0.980],
    "red":           [0.945, 0.220, 0.282],
    "muted_light":   [0.780, 0.815, 0.895],
}


def load_timing_file(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def resolve_palette(timing_data: Dict, overrides: Optional[Dict[str, List[float]]] = None) -> Dict[str, List[float]]:
    palette = dict(DEFAULT_PALETTE)
    raw = timing_data.get("palette", {})
    for key, val in raw.items():
        if isinstance(val, str):
            palette[key] = hex_to_rgb(val)
        elif isinstance(val, (list, tuple)) and len(val) >= 3:
            palette[key] = [float(val[0]), float(val[1]), float(val[2])]
    if overrides:
        palette.update(overrides)
    return palette


def resolve_color(color_spec, palette: Dict[str, List[float]], fallback: List[float]) -> List[float]:
    if not color_spec:
        return fallback
    if isinstance(color_spec, str):
        if color_spec.startswith("#"):
            return hex_to_rgb(color_spec)
        return palette.get(color_spec, fallback)
    if isinstance(color_spec, (list, tuple)) and len(color_spec) >= 3:
        return [float(color_spec[0]), float(color_spec[1]), float(color_spec[2])]
    return fallback


def validate_timing(timing_data: Dict) -> Tuple[List[str], List[Dict]]:
    """
    Validate a `lyrics_timing.json` payload.
    Returns `(errors, uncertain_cues)`.
    """
    errors: List[str] = []
    uncertain: List[Dict] = []

    sections = timing_data.get("sections", [])
    phrases = timing_data.get("phrases", [])
    if not sections:
        errors.append("Missing or empty 'sections' array.")

    sec_ids = set()
    prev_end = -1
    for i, s in enumerate(sections):
        sid = s.get("id")
        s0, s1 = s.get("start_ms"), s.get("end_ms")
        if not sid:
            errors.append(f"sections[{i}] missing 'id'.")
        elif sid in sec_ids:
            errors.append(f"Duplicate section id: {sid}")
        sec_ids.add(sid)
        if s0 is None or s1 is None or s1 <= s0:
            errors.append(f"Section {sid!r} has invalid bounds: start_ms={s0}, end_ms={s1}.")
        if prev_end >= 0 and s0 is not None and s0 < prev_end - 5:
            errors.append(f"Section {sid!r} overlaps previous section ({s0} < {prev_end}).")
        if s1 is not None:
            prev_end = s1

    seen_pids = set()
    for i, p in enumerate(phrases):
        pid = p.get("id", f"phrases[{i}]")
        if pid in seen_pids:
            errors.append(f"Duplicate phrase id: {pid}")
        seen_pids.add(pid)
        t0 = p.get("start_ms")
        t1 = p.get("end_ms")
        td = p.get("display_end_ms", t1)
        if t0 is None or t1 is None or t1 <= t0:
            errors.append(f"Phrase {pid!r} has invalid start/end: {t0}..{t1}")
        if td is not None and t1 is not None and td < t1:
            errors.append(f"Phrase {pid!r} has display_end_ms ({td}) < end_ms ({t1}).")
        sec = p.get("section")
        if sec and sec_ids and sec not in sec_ids:
            errors.append(f"Phrase {pid!r} references unknown section {sec!r}.")
        for wi, w in enumerate(p.get("words") or []):
            wt0, wt1 = w.get("start_ms"), w.get("end_ms")
            if wt0 is None or wt1 is None or wt1 <= wt0:
                errors.append(f"Phrase {pid!r} words[{wi}] has invalid bounds: {wt0}..{wt1}.")
        if p.get("uncertain"):
            uncertain.append({
                "id": pid,
                "section": sec,
                "start_ms": t0,
                "end_ms": t1,
                "text": p.get("text", ""),
                "review_note": p.get("review_note", ""),
            })

    return errors, uncertain


def emit_lyric_helpers(jb: JsxBuilder, margin_x: int = 70) -> None:
    """Emit EffectCraft JSX helpers for transparent RGBA lyric overlays."""
    max_x = jb.width - margin_x
    jb.w(
        f"""// Transparent RGBA Lyric Overlay Runtime (Zero Permanent Black Banner)
var LYR_MARGIN_X = {int(margin_x)};
var LYR_MAX_X = {int(max_x)};

function makeLyricComp(name, dur) {{
  var c = app.project.items.addComp(name, EC_W, EC_H, 1.0, dur, EC_FPS);
  c.bgColor = [0, 0, 0];
  return c;
}}

function styleLyricLayer(l, isEcho) {{
  var ds = l.property("Effects").addProperty("ADBE Drop Shadow");
  try {{
    ds.property("ADBE Drop Shadow-0001").setValue([0.015, 0.02, 0.05, 1.0]);
    ds.property("ADBE Drop Shadow-0002").setValue(isEcho ? 190 : 230);
    ds.property("ADBE Drop Shadow-0003").setValue(135);
    ds.property("ADBE Drop Shadow-0004").setValue(isEcho ? 4 : 5);
    ds.property("ADBE Drop Shadow-0005").setValue(isEcho ? 14 : 18);
  }} catch (e) {{}}
}}

function animateSingleLyric(l, cx, cy, anim, enterT, outT, isContIn, isContOut, compDur) {{
  var fadeOutDur = (anim === "still_hard") ? 0.04 : 0.14;
  var fadeInDur  = (anim === "still_hard") ? 0.02 : 0.11;
  var cIn  = Math.max(0, enterT);
  var cOut = Math.min(compDur, outT);
  if (cOut <= cIn + 0.01) return;

  if (anim === "sweep_room" && !isContIn) {{
    l.position.setValueAtTime(cIn, [EC_W + 460, cy]);
    l.position.setValueAtTime(Math.min(cOut, cIn + 0.34), [cx - 30, cy]);
    l.position.setValueAtTime(Math.min(cOut, cIn + 0.56), [cx, cy]);
    l.position.setValueAtTime(Math.max(cIn + 0.60, cOut - 0.30), [cx - 45, cy]);
    l.position.setValueAtTime(cOut, [-620, cy]);
    easeProp(l.position, 68);
    l.scale.setValueAtTime(cIn, [118, 118, 100]);
    l.scale.setValueAtTime(Math.min(cOut, cIn + 0.38), [100, 100, 100]);
    easeProp(l.scale, 65);
    l.opacity.setValueAtTime(cIn, 0);
    l.opacity.setValueAtTime(Math.min(cOut, cIn + 0.08), 100);
    if (!isContOut) {{
      l.opacity.setValueAtTime(Math.max(cIn + 0.10, cOut - 0.18), 100);
      l.opacity.setValueAtTime(cOut, 0);
    }}
    return;
  }}

  if (isContIn) {{
    l.position.setValue([cx, cy]);
    l.scale.setValue([100, 100, 100]);
    l.opacity.setValueAtTime(0, 100);
  }} else if (anim === "still_hard") {{
    l.position.setValue([cx, cy]);
    l.scale.setValue([100, 100, 100]);
    l.opacity.setValueAtTime(cIn, 100);
  }} else if (anim === "pop_snap") {{
    l.position.setValueAtTime(cIn, [cx, cy + 14]);
    l.position.setValueAtTime(Math.min(cOut, cIn + 0.14), [cx, cy]);
    easeProp(l.position, 70);
    l.scale.setValueAtTime(cIn, [86, 86, 100]);
    l.scale.setValueAtTime(Math.min(cOut, cIn + 0.09), [106, 106, 100]);
    l.scale.setValueAtTime(Math.min(cOut, cIn + 0.17), [100, 100, 100]);
    easeProp(l.scale, 65);
    l.opacity.setValueAtTime(cIn, 0);
    l.opacity.setValueAtTime(Math.min(cOut, cIn + 0.05), 100);
  }} else if (anim === "float_up") {{
    l.position.setValueAtTime(cIn, [cx, cy + 20]);
    l.position.setValueAtTime(Math.min(cOut, cIn + 0.22), [cx, cy]);
    l.position.setValueAtTime(cOut, [cx, cy - 10]);
    easeProp(l.position, 60);
    l.opacity.setValueAtTime(cIn, 0);
    l.opacity.setValueAtTime(Math.min(cOut, cIn + 0.12), 92);
  }} else {{
    l.position.setValueAtTime(cIn, [cx, cy + 16]);
    l.position.setValueAtTime(Math.min(cOut, cIn + 0.16), [cx, cy]);
    easeProp(l.position, 72);
    l.opacity.setValueAtTime(cIn, 0);
    l.opacity.setValueAtTime(Math.min(cOut, cIn + fadeInDur), 100);
  }}

  if (!isContOut) {{
    var foStart = Math.max(cIn + fadeInDur + 0.02, cOut - fadeOutDur);
    l.opacity.setValueAtTime(foStart, (anim === "float_up") ? 92 : 100);
    l.opacity.setValueAtTime(cOut, 0);
  }}
}}

function addChunkedPhrase(comp, chunksSpec, anchorX, yPos, align, fontSize, defaultRgb, phraseOutT, anim, isEcho, compDur, fontName) {{
  var gapPx = Math.round(fontSize * 0.28);
  var layers = [];
  var widths = [];
  var totalW = 0;

  for (var i = 0; i < chunksSpec.length; i++) {{
    var ch = chunksSpec[i];
    var cIn = Math.max(0, ch.startT);
    var cOut = Math.min(compDur, phraseOutT);
    if (cOut <= cIn + 0.01) {{
      layers.push(null); widths.push(0); continue;
    }}
    var col = ch.rgb || defaultRgb;
    var style = isEcho ? "Bold Italic" : "Black";
    var l = makeText(comp, ch.text, fontSize, style, col, "left", cIn, cOut, fontName);
    styleLyricLayer(l, isEcho);
    var r = l.sourceRectAtTime(Math.min(cOut - 0.01, cIn + 0.05), false);
    var lw = Math.max(12, r.width);
    widths.push(lw);
    totalW += lw;
    if (i < chunksSpec.length - 1) totalW += gapPx;
    layers.push(l);
  }}

  var curX = anchorX;
  if (align === "center") curX = anchorX - totalW / 2.0;
  else if (align === "right") curX = anchorX - totalW;

  if (curX < LYR_MARGIN_X) curX = LYR_MARGIN_X;
  if (curX + totalW > LYR_MAX_X) curX = Math.max(LYR_MARGIN_X, LYR_MAX_X - totalW);

  for (var i = 0; i < layers.length; i++) {{
    var l = layers[i];
    if (!l) continue;
    var ch = chunksSpec[i];
    var isContIn = (ch.startT < 0);
    var isContOut = (phraseOutT > compDur + 0.005);
    var chAnim = ch.accent ? "pop_snap" : anim;
    if (anim === "still_hard") chAnim = "still_hard";
    animateSingleLyric(l, curX, yPos, chAnim, ch.startT, phraseOutT, isContIn, isContOut, compDur);
    curX += widths[i] + gapPx;
  }}
}}
"""
    )


def comp_name_for_section(sec_id: str, prefix: str = "L") -> str:
    """Turn 'S01_Intro' -> 'L01_Intro' (or prepend prefix if no leading 'S')."""
    if len(sec_id) >= 2 and sec_id[0] == "S" and sec_id[1].isdigit():
        return prefix + sec_id[1:]
    return f"{prefix}_{sec_id}"


def build_all_lyrics(
    jb: JsxBuilder,
    timing_data: Dict,
    comp_prefix: str = "L",
    margin_x: int = 70,
    palette_overrides: Optional[Dict[str, List[float]]] = None,
) -> List[str]:
    """
    Emit one transparent RGBA lyric overlay composition per non-instrumental section.
    Returns the list of generated composition names.
    """
    fps = float(timing_data.get("meta", {}).get("fps", jb.fps))
    sections = timing_data.get("sections", [])
    phrases = timing_data.get("phrases", [])
    bounds = frame_aligned_sections(sections, fps=fps)
    palette = resolve_palette(timing_data, palette_overrides)

    emit_lyric_helpers(jb, margin_x=margin_x)

    built_comps: List[str] = []
    for sec in sections:
        sec_id = sec["id"]
        t0, t1, dur, _frames = bounds[sec_id]
        t0_ms = t0 * 1000.0
        t1_ms = t1 * 1000.0

        active = [
            p for p in phrases
            if p["start_ms"] < t1_ms - 10 and p.get("display_end_ms", p["end_ms"]) > t0_ms + 10
        ]
        if not active:
            continue

        comp_name = comp_name_for_section(sec_id, prefix=comp_prefix)
        cvar = f"lc_{sec_id}"
        jb.w(f'var {cvar} = makeLyricComp({json.dumps(comp_name)}, {dur:.4f});')
        built_comps.append(comp_name)

        for p in active:
            lay = p.get("layout", {})
            x = lay.get("x", jb.width // 2)
            y = lay.get("y", 118)
            align = lay.get("align", "center")
            size = lay.get("size", 56)
            font_name = lay.get("font") or jb.default_font
            rgb = resolve_color(lay.get("color", "cream"), palette, palette["cream"])
            anim = lay.get("anim", "slide_settle")
            is_echo = (p.get("type") == "echo")

            lt_in = round((p["start_ms"] - t0_ms) / 1000.0, 4)
            lt_out = round((p.get("display_end_ms", p["end_ms"]) - t0_ms) / 1000.0, 4)

            if p.get("words"):
                chunks = []
                for w in p["words"]:
                    w_in = round((w["start_ms"] - t0_ms) / 1000.0, 4)
                    acc_key = w.get("accent")
                    w_rgb = resolve_color(acc_key, palette, rgb) if acc_key else rgb
                    chunks.append({
                        "text": w["text"],
                        "startT": w_in,
                        "rgb": w_rgb,
                        "accent": bool(acc_key),
                    })
                jb.w(
                    f'addChunkedPhrase({cvar}, {json.dumps(chunks)}, {x}, {y}, {json.dumps(align)}, '
                    f'{size}, {json.dumps(rgb)}, {lt_out:.4f}, {json.dumps(anim)}, '
                    f'{"true" if is_echo else "false"}, {dur:.4f}, {json.dumps(font_name)});'
                )
            else:
                lvar = jb.uid("lyr")
                c_in = max(0.0, lt_in)
                c_out = min(dur, lt_out)
                if c_out <= c_in + 0.01:
                    continue
                style = "Bold Italic" if is_echo else "Black"
                is_cont_in = "true" if lt_in < 0.0 else "false"
                is_cont_out = "true" if lt_out > dur + 0.005 else "false"
                jb.w(
                    f'var {lvar} = makeText({cvar}, {json.dumps(p["text"])}, {size}, '
                    f'{json.dumps(style)}, {json.dumps(rgb)}, {json.dumps(align)}, '
                    f'{c_in:.4f}, {c_out:.4f}, {json.dumps(font_name)});'
                )
                jb.w(f'styleLyricLayer({lvar}, {"true" if is_echo else "false"});')
                if anim == "sweep_room":
                    jb.w(f'addGlowFX({lvar}, 35, 36, 1.35);')
                jb.w(
                    f'animateSingleLyric({lvar}, {x}, {y}, {json.dumps(anim)}, {lt_in:.4f}, '
                    f'{lt_out:.4f}, {is_cont_in}, {is_cont_out}, {dur:.4f});'
                )

    return built_comps


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate lyrics_timing.json or generate EffectCraft lyric JSX.")
    parser.add_argument("--timing", type=Path, required=True, help="Path to editable lyrics_timing.json.")
    parser.add_argument("--validate", action="store_true", help="Validate JSON schema and list uncertain cues.")
    parser.add_argument("--out-jsx", type=Path, help="Optional output JSX file with standalone lyric comps.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--font", type=str, default=DEFAULT_FONT)
    parser.add_argument("--prefix", type=str, default="L", help="Lyric comp name prefix (default: L).")
    args = parser.parse_args(argv)

    data = load_timing_file(args.timing)
    errors, uncertain = validate_timing(data)

    if args.validate or not args.out_jsx:
        secs = data.get("sections", [])
        phrases = data.get("phrases", [])
        print(f"Timing file: {args.timing} ({len(secs)} sections, {len(phrases)} phrases)")
        if errors:
            print(f"ERRORS ({len(errors)}):")
            for err in errors:
                print(f"  - {err}")
            return 1
        print("Validation: OK (0 errors)")
        if uncertain:
            print(f"Uncertain cues flagged for manual review ({len(uncertain)}):")
            for u in uncertain:
                print(
                    f"  - [{u['id']}] ({u['section']}) {u['start_ms']}..{u['end_ms']} ms "
                    f"\"{u['text']}\" -> {u['review_note']}"
                )
        else:
            print("Uncertain cues: none")

    if args.out_jsx:
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        fps = float(data.get("meta", {}).get("fps", DEFAULT_FPS))
        jb = JsxBuilder(width=args.width, height=args.height, fps=fps, default_font=args.font)
        comps = build_all_lyrics(jb, data, comp_prefix=args.prefix)
        jb.w(f'writeLn("BUILT {len(comps)} LYRIC COMPS: " + {json.dumps(", ".join(comps))});')
        jb.write_jsx(args.out_jsx)
        print(f"Wrote lyric JSX ({len(comps)} comps, {len(jb.lines)} lines) -> {args.out_jsx}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
