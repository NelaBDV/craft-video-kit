#!/usr/bin/env python3
"""
ec_runtime.py — Reusable EffectCraft 2D animation JSX builder & runtime library.

Project-agnostic helpers extracted for intros, demos, short 2D scenes, and music videos:
  - JsxBuilder: emits clean ExtendScript/JSX for EffectCraft headless CLI
  - Zero-anchor camera nulls (`makeCamNull`) and `cam_focus()` world-to-camera math
  - Vector shapes (`addPoly` with Bezier tangents, `addRect`, `addEllipse`)
  - Lighting & compositing helpers (`addRadialGlow`, `addLinearGradientBg`, `addGlowFX`, `addDropShadowFX`)
  - Eased and stepped/hold keyframes (`easeProp`, `holdKey`, `setKeys`, `setHoldKeys`)
  - CLI runner for `effectcraft-cli` (auto-detecting native binary vs Flatpak)

Dependencies: Python 3.9+ (standard library only), effectcraft-cli (native or Flatpak).
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30.0
DEFAULT_FONT = "Adwaita Sans"


def hex_to_rgb(hex_color: str) -> List[float]:
    """Convert '#RRGGBB' (or 'RRGGBB') to EffectCraft RGB floats [0..1]."""
    h = hex_color.lstrip("#").strip()
    if len(h) != 6:
        raise ValueError(f"Expected 6-digit hex color, got: {hex_color!r}")
    return [round(int(h[i:i + 2], 16) / 255.0, 4) for i in (0, 2, 4)]


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> List[float]:
    """Convert '#RRGGBB' to EffectCraft RGBA floats [0..1]."""
    return hex_to_rgb(hex_color) + [round(float(alpha), 4)]


def cam_focus(
    tx: float,
    ty: float,
    scale_pct: float = 100.0,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> List[float]:
    """
    Return exact [x, y] position for a zero-anchor camera null (`anchorPoint=[0,0]`)
    so that world coordinate (tx, ty) lands at frame center (width/2, height/2)
    at scale `scale_pct`%.
    """
    s = scale_pct / 100.0
    return [round(width / 2.0 - s * tx, 1), round(height / 2.0 - s * ty, 1)]


def frame_aligned_sections(
    sections: Sequence[Dict],
    fps: float = DEFAULT_FPS,
) -> Dict[str, Tuple[float, float, float, int]]:
    """
    Convert a list of section dicts (`id`, `start_ms`, `end_ms`) into frame-aligned
    bounds: `{section_id: (t0_sec, t1_sec, dur_sec, num_frames)}` with zero drift.
    """
    out: Dict[str, Tuple[float, float, float, int]] = {}
    for sec in sections:
        f0 = int(round((sec["start_ms"] / 1000.0) * fps))
        f1 = int(round((sec["end_ms"] / 1000.0) * fps))
        frames = max(1, f1 - f0)
        out[sec["id"]] = (f0 / fps, f1 / fps, frames / fps, frames)
    return out


def detect_effectcraft_cmd(filesystem_roots: Optional[Sequence[Path]] = None) -> List[str]:
    """Return base command for `effectcraft-cli` (native binary if on PATH, else Flatpak)."""
    native = shutil.which("effectcraft-cli")
    if native:
        return [native]
    cmd = ["flatpak", "run"]
    for root in (filesystem_roots or []):
        cmd.append(f"--filesystem={Path(root).resolve()}")
    cmd += ["--command=effectcraft-cli", "ai.storyteller.effectcraft"]
    return cmd


def run_effectcraft_script(
    jsx_path: Path,
    project_out: Path,
    filesystem_roots: Optional[Sequence[Path]] = None,
    low_load: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a generated JSX script in EffectCraft headless CLI and save `.ecproj`."""
    roots = list(filesystem_roots or [])
    roots.extend([jsx_path.resolve().parent, project_out.resolve().parent])
    unique_roots = list(dict.fromkeys(roots))

    cmd = detect_effectcraft_cmd(unique_roots) + [
        "--empty", "script", str(jsx_path.resolve()),
        "--save-as", str(project_out.resolve()),
    ]
    if low_load and shutil.which("nice"):
        cmd = ["nice", "-n", "15"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class JsxBuilder:
    """
    Incremental JSX builder for EffectCraft 2D scenes and overlays.

    CRITICAL EffectCraft / AE rules encoded by the generated runtime:
    1. `makeCamNull` zeros `anchorPoint` to `[0, 0]` and sets `parent` BEFORE `position`.
    2. Always attach ALL child layers while the parent is at neutral transform
       (`rotation = 0`, `scale = [100, 100]`); animate parent transforms AFTERWARDS.
    3. Inside one Shape layer (`ADBE Root Vectors Group`), the FIRST added group renders
       ON TOP (front-to-back). Across separate Comp layers, each new layer inserts at
       index 1 (ON TOP), so create layers back-to-front.
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: float = DEFAULT_FPS,
        default_font: str = DEFAULT_FONT,
        include_helpers: bool = True,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.default_font = default_font
        self.lines: List[str] = []
        self._uid = 0
        if include_helpers:
            self._write_runtime()

    def uid(self, prefix: str = "v") -> str:
        self._uid += 1
        return f"{prefix}_{self._uid}"

    def w(self, line: str) -> None:
        self.lines.append(line)

    def render_source(self) -> str:
        return "\n".join(self.lines) + "\n"

    def write_jsx(self, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.render_source(), encoding="utf-8")
        return out_path

    def _write_runtime(self) -> None:
        w, h, fps = self.width, self.height, self.fps
        cx, cy = w / 2.0, h / 2.0
        font_js = json.dumps(self.default_font)
        self.w(
            f"""// Shared EffectCraft 2D Runtime ({w}x{h} @ {fps}fps)
var EC_W = {w};
var EC_H = {h};
var EC_FPS = {fps};
var EC_DEFAULT_FONT = {font_js};

function makeComp(name, dur, bgRgb) {{
  var c = app.project.items.addComp(name, EC_W, EC_H, 1.0, dur, EC_FPS);
  if (bgRgb) c.bgColor = bgRgb;
  return c;
}}

function easeProp(prop, infl) {{
  var inf = infl || 68;
  var e = new KeyframeEase(0, inf);
  var n = prop.numKeys;
  if (n < 2) return;
  var v = prop.keyValue(1);
  var dims = (v && v.length) ? v.length : 1;
  var arr = [];
  if (
    prop.matchName === "ADBE Position" ||
    prop.matchName === "ADBE Anchor Point" ||
    prop.matchName === "ADBE Vector Position"
  ) {{
    arr = [e];
  }} else {{
    for (var d = 0; d < dims; d++) arr.push(e);
  }}
  for (var k = 1; k <= n; k++) {{
    try {{ prop.setTemporalEaseAtKey(k, arr, arr); }} catch (err) {{}}
  }}
}}

function holdKey(prop, keyIdx) {{
  try {{
    prop.setInterpolationTypeAtKey(
      keyIdx,
      KeyframeInterpolationType.HOLD,
      KeyframeInterpolationType.HOLD
    );
  }} catch (err) {{}}
}}

function setKeys(prop, pairs, easeInfl) {{
  for (var i = 0; i < pairs.length; i++) {{
    prop.setValueAtTime(pairs[i][0], pairs[i][1]);
  }}
  if (easeInfl !== 0) easeProp(prop, easeInfl || 65);
}}

function setHoldKeys(prop, pairs) {{
  for (var i = 0; i < pairs.length; i++) {{
    prop.setValueAtTime(pairs[i][0], pairs[i][1]);
  }}
  for (var k = 1; k <= prop.numKeys; k++) holdKey(prop, k);
}}

function addPoly(contents, name, pts, closed, fillCol, strokeCol, sw, op, inT, outT) {{
  var g = contents.addProperty("ADBE Vector Group");
  g.name = name;
  var gc = g.property("ADBE Vectors Group");
  var p = gc.addProperty("ADBE Vector Shape - Group");
  var s = new Shape();
  s.vertices = pts;
  if (inT) s.inTangents = inT;
  if (outT) s.outTangents = outT;
  s.closed = closed;
  p.property("ADBE Vector Shape").setValue(s);
  var st = null;
  if (strokeCol !== null && sw > 0) {{
    st = gc.addProperty("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Color").setValue(strokeCol);
    st.property("ADBE Vector Stroke Width").setValue(sw);
    st.property("ADBE Vector Stroke Line Cap").setValue(2);
    st.property("ADBE Vector Stroke Line Join").setValue(2);
  }}
  var fl = null;
  if (fillCol !== null) {{
    fl = gc.addProperty("ADBE Vector Graphic - Fill");
    fl.property("ADBE Vector Fill Color").setValue(fillCol);
  }}
  var tr = g.property("ADBE Vector Transform Group");
  if (op !== undefined) tr.property("ADBE Vector Group Opacity").setValue(op);
  return {{group: g, path: p.property("ADBE Vector Shape"), stroke: st, fill: fl, tr: tr}};
}}

function addRect(contents, name, w, h, fillCol, strokeCol, sw, op, pos, roundness) {{
  var g = contents.addProperty("ADBE Vector Group");
  g.name = name;
  var gc = g.property("ADBE Vectors Group");
  var rc = gc.addProperty("ADBE Vector Shape - Rect");
  rc.property("ADBE Vector Rect Size").setValue([w, h]);
  if (roundness) rc.property("ADBE Vector Rect Roundness").setValue(roundness);
  var st = null;
  if (strokeCol !== null && sw > 0) {{
    st = gc.addProperty("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Color").setValue(strokeCol);
    st.property("ADBE Vector Stroke Width").setValue(sw);
    st.property("ADBE Vector Stroke Line Join").setValue(2);
  }}
  var fl = null;
  if (fillCol !== null) {{
    fl = gc.addProperty("ADBE Vector Graphic - Fill");
    fl.property("ADBE Vector Fill Color").setValue(fillCol);
  }}
  var tr = g.property("ADBE Vector Transform Group");
  if (pos) tr.property("ADBE Vector Position").setValue(pos);
  if (op !== undefined) tr.property("ADBE Vector Group Opacity").setValue(op);
  return {{group: g, rect: rc, stroke: st, fill: fl, tr: tr}};
}}

function addEllipse(contents, name, rx, ry, fillCol, strokeCol, sw, op, pos) {{
  var g = contents.addProperty("ADBE Vector Group");
  g.name = name;
  var gc = g.property("ADBE Vectors Group");
  var el = gc.addProperty("ADBE Vector Shape - Ellipse");
  el.property("ADBE Vector Ellipse Size").setValue([rx * 2, ry * 2]);
  var st = null;
  if (strokeCol !== null && sw > 0) {{
    st = gc.addProperty("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Color").setValue(strokeCol);
    st.property("ADBE Vector Stroke Width").setValue(sw);
    st.property("ADBE Vector Stroke Line Cap").setValue(2);
  }}
  var fl = null;
  if (fillCol !== null) {{
    fl = gc.addProperty("ADBE Vector Graphic - Fill");
    fl.property("ADBE Vector Fill Color").setValue(fillCol);
  }}
  var tr = g.property("ADBE Vector Transform Group");
  if (pos) tr.property("ADBE Vector Position").setValue(pos);
  if (op !== undefined) tr.property("ADBE Vector Group Opacity").setValue(op);
  return {{group: g, ellipse: el, stroke: st, fill: fl, tr: tr}};
}}

function addRadialGlow(comp, name, centerPt, radiusPx, colRgba, opacityPct, inT, outT, parentLayer) {{
  var l = comp.layers.addSolid([0, 0, 0], name, EC_W, EC_H, 1.0);
  l.inPoint = inT; l.outPoint = outT;
  var ramp = l.property("Effects").addProperty("ADBE Ramp");
  ramp.property("ADBE Ramp-0001").setValue(centerPt);
  ramp.property("ADBE Ramp-0002").setValue(colRgba);
  ramp.property("ADBE Ramp-0003").setValue([centerPt[0], centerPt[1] + radiusPx]);
  ramp.property("ADBE Ramp-0004").setValue([0, 0, 0, 1]);
  ramp.property("ADBE Ramp-0005").setValue(2); // Radial
  l.blendingMode = BlendingMode.ADD;
  l.opacity.setValue(opacityPct);
  if (parentLayer) {{
    l.parent = parentLayer;
    l.position.setValue([{cx}, {cy}]);
  }}
  return l;
}}

function addLinearGradientBg(comp, name, p1, c1, p2, c2, inT, outT, parentLayer) {{
  var l = comp.layers.addSolid([0, 0, 0], name, EC_W, EC_H, 1.0);
  l.inPoint = inT; l.outPoint = outT;
  var ramp = l.property("Effects").addProperty("ADBE Ramp");
  ramp.property("ADBE Ramp-0001").setValue(p1);
  ramp.property("ADBE Ramp-0002").setValue(c1);
  ramp.property("ADBE Ramp-0003").setValue(p2);
  ramp.property("ADBE Ramp-0004").setValue(c2);
  ramp.property("ADBE Ramp-0005").setValue(1); // Linear
  if (parentLayer) {{
    l.parent = parentLayer;
    l.position.setValue([{cx}, {cy}]);
  }}
  return l;
}}

function addGlowFX(layer, threshold, radius, intensity) {{
  var g = layer.property("Effects").addProperty("ADBE Glo2");
  g.property("ADBE Glo2-0002").setValue(threshold !== undefined ? threshold : 45);
  g.property("ADBE Glo2-0003").setValue(radius !== undefined ? radius : 36);
  g.property("ADBE Glo2-0004").setValue(intensity !== undefined ? intensity : 1.2);
  return g;
}}

function addDropShadowFX(layer, opacity255, dist, softness, dirDeg, shadowRgba) {{
  var ds = layer.property("Effects").addProperty("ADBE Drop Shadow");
  try {{
    ds.property("ADBE Drop Shadow-0001").setValue(shadowRgba || [0.02, 0.03, 0.07, 1.0]);
    ds.property("ADBE Drop Shadow-0002").setValue(opacity255 !== undefined ? opacity255 : 210);
    ds.property("ADBE Drop Shadow-0003").setValue(dirDeg !== undefined ? dirDeg : 135);
    ds.property("ADBE Drop Shadow-0004").setValue(dist !== undefined ? dist : 6);
    ds.property("ADBE Drop Shadow-0005").setValue(softness !== undefined ? softness : 16);
  }} catch (e) {{}}
  return ds;
}}

function makeText(comp, txt, fontSize, styleName, colRgb, align, inT, outT, fontName) {{
  var l = comp.layers.addText(txt);
  var td = l.property("Source Text").value;
  td.font = fontName || EC_DEFAULT_FONT;
  td.fontStyle = styleName || "Black";
  td.fontSize = fontSize;
  td.fillColor = [colRgb[0], colRgb[1], colRgb[2]];
  if (align === "left") td.justification = ParagraphJustification.LEFT_JUSTIFY;
  else if (align === "right") td.justification = ParagraphJustification.RIGHT_JUSTIFY;
  else td.justification = ParagraphJustification.CENTER_JUSTIFY;
  l.property("Source Text").setValue(td);
  l.inPoint = inT;
  l.outPoint = outT;
  return l;
}}

function makeCamNull(comp, name, inT, outT, pos, sc, parentLayer) {{
  var n = comp.layers.addNull();
  n.name = name;
  n.inPoint = inT; n.outPoint = outT;
  n.anchorPoint.setValue([0, 0]);
  if (parentLayer) n.parent = parentLayer;
  n.position.setValue(pos || [{cx}, {cy}]);
  if (sc) n.scale.setValue([sc, sc, 100]);
  return n;
}}

function makeShapeLayer(comp, name, inT, outT, pos, parentLayer) {{
  var l = comp.layers.addShape();
  l.name = name;
  l.inPoint = inT; l.outPoint = outT;
  if (parentLayer) l.parent = parentLayer;
  l.position.setValue(pos || [0, 0]);
  return l;
}}
"""
        )


def check_environment() -> Dict[str, str]:
    """Inspect local availability of required CLI tools (native or Flatpak) without launching renders."""
    status: Dict[str, str] = {}
    for tool in ("python3", "ffmpeg", "ffprobe", "flatpak", "nice", "ionice", "taskset"):
        found = shutil.which(tool)
        status[tool] = found if found else "missing"

    flatpak_apps = {
        "effectcraft-cli": "ai.storyteller.effectcraft",
        "filmcraft-cli": "ai.storyteller.filmcraft",
    }
    for cli_name, app_id in flatpak_apps.items():
        native = shutil.which(cli_name)
        if native:
            status[cli_name] = native
        elif status["flatpak"] != "missing":
            res = subprocess.run(
                ["flatpak", "info", app_id],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            status[cli_name] = f"flatpak:{app_id}" if res.returncode == 0 else "missing"
        else:
            status[cli_name] = "missing"
    return status


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EffectCraft 2D runtime helper & environment check.")
    parser.add_argument("--check-env", action="store_true", help="Print detected CLI tool paths.")
    parser.add_argument("--emit-runtime", type=Path, help="Write standalone JSX runtime helpers to a file.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--font", type=str, default=DEFAULT_FONT)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check_env:
        print(json.dumps(check_environment(), indent=2))
        return 0
    if args.emit_runtime:
        jb = JsxBuilder(width=args.width, height=args.height, fps=args.fps, default_font=args.font)
        jb.write_jsx(args.emit_runtime)
        print(f"Wrote JSX runtime ({len(jb.lines)} lines) -> {args.emit_runtime}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
