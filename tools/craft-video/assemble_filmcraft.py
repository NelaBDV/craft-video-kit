#!/usr/bin/env python3
"""
assemble_filmcraft.py — Project-agnostic FilmCraft timeline assembler & dual-master exporter.

Works for BOTH:
  - Music videos: V1 (opaque 2D/VFX sections) + V2 (transparent ProRes 4444 RGBA lyrics)
    + A1 (original master audio untouched at 0.0 dB), exporting both Master (with lyrics)
    and Clean (V2 disabled, preserving all diegetic set text on V1) MP4s from the exact same edit.
  - Standalone 2D animations (intros, demos, short scenes): with or without audio,
    with or without V2 title/HUD overlay track.

Dependencies: Python 3.9+ (standard library only), filmcraft-cli (native or Flatpak), ffprobe.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


TICKS_PER_SEC = 254016000000


def detect_filmcraft_cmd(low_load: bool = True, cores: Optional[str] = None) -> List[str]:
    prefix: List[str] = []
    if low_load:
        if shutil.which("nice"):
            prefix += ["nice", "-n", "15"]
        if shutil.which("ionice"):
            prefix += ["ionice", "-c", "3"]
        if cores and shutil.which("taskset"):
            prefix += ["taskset", "-c", cores]
    native = shutil.which("filmcraft-cli")
    if native:
        return prefix + [native]
    return prefix + ["flatpak", "run", "--command=filmcraft-cli", "ai.storyteller.filmcraft"]


def run_fc(
    args: List[str],
    low_load: bool = True,
    threads: int = 2,
    cores: Optional[str] = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if low_load:
        env["RAYON_NUM_THREADS"] = str(threads)
        env["OMP_NUM_THREADS"] = str(threads)
    cmd = detect_filmcraft_cmd(low_load=low_load, cores=cores) + args
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(
            f"filmcraft-cli failed ({res.returncode}):\n"
            f"CMD: {' '.join(cmd)}\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        )
    return res


def probe_media(path: Path) -> Dict:
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,size",
            "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(res.stdout)


def section_comp_name(sec_id: str, prefix: str) -> str:
    if len(sec_id) >= 2 and sec_id[0] == "S" and sec_id[1].isdigit():
        return prefix + sec_id[1:]
    return f"{prefix}_{sec_id}"


def build_clip_plan_from_timing(
    timing_path: Path,
    renders_dir: Path,
    v1_prefix: str,
    v2_prefix: str,
    fps_override: Optional[float],
) -> Tuple[float, List[Tuple[Path, int, str]], List[Tuple[Path, int, str]], List[Tuple[float, str, str]], Optional[Path]]:
    data = json.loads(timing_path.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    fps = float(fps_override or meta.get("fps", 30.0))

    v1_clips: List[Tuple[Path, int, str]] = []
    v2_clips: List[Tuple[Path, int, str]] = []
    markers: List[Tuple[float, str, str]] = []

    for sec in data.get("sections", []):
        sid = sec["id"]
        f0 = int(round((sec["start_ms"] / 1000.0) * fps))
        v1_path = renders_dir / f"{section_comp_name(sid, v1_prefix)}.mov"
        v1_clips.append((v1_path, f0, sid))

        v2_path = renders_dir / f"{section_comp_name(sid, v2_prefix)}.mov"
        if v2_path.exists():
            v2_clips.append((v2_path, f0, sid))

        markers.append((f0 / fps, sec.get("label", sid), "Violet"))

    if meta.get("last_accent_ms"):
        markers.append((meta["last_accent_ms"] / 1000.0, "Last Accent", "Yellow"))
    if meta.get("black_cut_ms"):
        markers.append((meta["black_cut_ms"] / 1000.0, "Black Cut", "Red"))
    if meta.get("audio_duration_ms"):
        markers.append((meta["audio_duration_ms"] / 1000.0, "Audio End", "Green"))

    audio_hint = None
    if meta.get("audio_file"):
        cand = Path(meta["audio_file"])
        if not cand.is_absolute():
            cand = (timing_path.parent.parent / cand).resolve()
        if cand.exists():
            audio_hint = cand

    return fps, v1_clips, v2_clips, markers, audio_hint


def build_clip_plan_from_lists(
    v1_list: List[Path],
    v2_list: List[Path],
    fps: float,
) -> Tuple[List[Tuple[Path, int, str]], List[Tuple[Path, int, str]]]:
    v1_clips: List[Tuple[Path, int, str]] = []
    cursor_f = 0
    for p in v1_list:
        v1_clips.append((p.resolve(), cursor_f, p.stem))
        if p.exists():
            dur = float(probe_media(p)["format"]["duration"])
            cursor_f += int(round(dur * fps))

    v2_clips: List[Tuple[Path, int, str]] = []
    cursor_f2 = 0
    for p in v2_list:
        v2_clips.append((p.resolve(), cursor_f2, p.stem))
        if p.exists():
            dur = float(probe_media(p)["format"]["duration"])
            cursor_f2 += int(round(dur * fps))

    return v1_clips, v2_clips


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble FilmCraft project & export Master / Clean MP4s.")
    parser.add_argument("--out-fcproj", type=Path, required=True, help="Output .fcproj path.")
    parser.add_argument("--project-name", default="Craft_2D_Project", help="FilmCraft internal project name.")
    parser.add_argument("--sequence-name", default="Master_1080p", help="Master sequence name.")
    parser.add_argument("--timing", type=Path, help="Optional editable lyrics_timing.json (sections & markers).")
    parser.add_argument("--renders-dir", type=Path, help="Directory with V*.mov / L*.mov renders (used with --timing).")
    parser.add_argument("--v1-prefix", default="V", help="V1 comp filename prefix with --timing (default: V).")
    parser.add_argument("--v2-prefix", default="L", help="V2 overlay comp prefix with --timing (default: L).")
    parser.add_argument("--v1-clips", help="Comma-separated V1 clip paths (alternative to --timing).")
    parser.add_argument("--v2-clips", help="Optional comma-separated V2 RGBA overlay clip paths.")
    parser.add_argument("--audio", type=Path, help="Optional master audio path (MP3/WAV/FLAC).")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=None, help="Frame rate (default: timing meta.fps or 30).")
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--normalize-db", type=float, default=None, help="Optional mix normalization dB (omit to keep audio untouched).")
    parser.add_argument("--export-master", type=Path, help="Optional MP4 export with V2 enabled.")
    parser.add_argument("--export-clean", type=Path, help="Optional MP4 export with V2 disabled (diegetic V1 kept).")
    parser.add_argument("--preset", default="High Quality 1080p HD", help="FilmCraft export preset.")
    parser.add_argument("--low-load", action="store_true", default=True, help="Cap threads & use nice/ionice (default: on).")
    parser.add_argument("--no-low-load", dest="low_load", action="store_false")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--cores", type=str, default=None, help="Optional taskset core range (e.g. '0-3').")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without invoking filmcraft-cli.")
    args = parser.parse_args(argv)

    markers: List[Tuple[float, str, str]] = []
    audio_path: Optional[Path] = args.audio.resolve() if args.audio else None

    if args.timing:
        if not args.renders_dir:
            parser.error("--renders-dir is required when using --timing.")
        fps, v1_clips, v2_clips, markers, audio_hint = build_clip_plan_from_timing(
            args.timing.resolve(), args.renders_dir.resolve(), args.v1_prefix, args.v2_prefix, args.fps
        )
        if audio_path is None:
            audio_path = audio_hint
    elif args.v1_clips:
        fps = float(args.fps or 30.0)
        v1_paths = [Path(p.strip()) for p in args.v1_clips.split(",") if p.strip()]
        v2_paths = [Path(p.strip()) for p in (args.v2_clips or "").split(",") if p.strip()]
        v1_clips, v2_clips = build_clip_plan_from_lists(v1_paths, v2_paths, fps)
    else:
        parser.error("Provide either --timing + --renders-dir OR --v1-clips.")

    has_v2 = bool(v2_clips)
    has_audio = audio_path is not None

    if args.dry_run:
        print(f"[DRY-RUN] Project: {args.out_fcproj} ({args.width}x{args.height} @ {fps}fps, Rec.709)")
        print(f"  V1 clips ({len(v1_clips)}): " + ", ".join(f"{p.name}@{f}" for p, f, _ in v1_clips))
        print(f"  V2 overlays ({len(v2_clips)}): " + (", ".join(f"{p.name}@{f}" for p, f, _ in v2_clips) or "none"))
        print(f"  A1 audio: {audio_path or 'none (silent video)'}")
        print(f"  Markers: {len(markers)}")
        print(f"  Export master: {args.export_master or 'none'}")
        print(f"  Export clean : {args.export_clean or 'none'}")
        return 0

    for p, _, _ in v1_clips + v2_clips:
        if not p.exists():
            raise FileNotFoundError(f"Missing render clip: {p}")
    if audio_path and not audio_path.exists():
        raise FileNotFoundError(f"Missing audio file: {audio_path}")

    out_fcproj = args.out_fcproj.resolve()
    out_fcproj.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="craft_fc_") as td:
        tmp = Path(td)

        # 1. Create project + Rec.709 sequence
        init_jsonl = tmp / "fc_init.jsonl"
        init_jsonl.write_text("\n".join([
            json.dumps({"id": "file.newProject", "params": {"name": args.project_name}}),
            json.dumps({
                "id": "file.newSequence",
                "params": {
                    "name": args.sequence_name,
                    "width": args.width, "height": args.height,
                    "fps": fps, "sampleRate": args.sample_rate,
                    "video": 2 if has_v2 else 1,
                    "audio": 1 if has_audio else 0,
                },
            }),
            json.dumps({"id": "sequence.colorSettings", "params": {"workingSpace": "rec709"}}),
        ]) + "\n", encoding="utf-8")
        run_fc(["--save-as", str(out_fcproj), "run", str(init_jsonl)], args.low_load, args.threads, args.cores)

        # 2. Import media
        media_paths: List[str] = []
        if audio_path:
            media_paths.append(str(audio_path))
        media_paths += [str(p) for p, _, _ in v1_clips]
        media_paths += [str(p) for p, _, _ in v2_clips]
        run_fc(["--project", str(out_fcproj), "--save", "import"] + media_paths, args.low_load, args.threads, args.cores)

        proj_json = json.loads(
            run_fc(["--project", str(out_fcproj), "inspect", "project"], args.low_load, args.threads, args.cores).stdout
        )
        name_to_id = {child["name"]: child["item"] for child in proj_json["root"]["children"]}

        # 3. Assemble timeline (exact frame placement)
        steps: List[Dict] = [
            {"id": "timeline.setTrack", "params": {"track": "V1", "name": "Scenes_2D", "enabled": True}},
        ]
        if has_v2:
            steps.append({"id": "timeline.setTrack", "params": {"track": "V2", "name": "Overlay_RGBA", "enabled": True}})
        if audio_path:
            steps.append({"id": "timeline.setTrack", "params": {"track": "A1", "name": "Audio_Master", "volumeDb": 0.0}})
            steps.append({
                "id": "timeline.place",
                "params": {"item": name_to_id[audio_path.name], "track": "A1", "seconds": 0.0, "video": False, "audio": True},
            })

        for p, f0, _ in v1_clips:
            steps.append({
                "id": "timeline.place",
                "params": {"item": name_to_id[p.name], "track": "V1", "frame": f0, "video": True, "audio": False},
            })
        for p, f0, _ in v2_clips:
            steps.append({
                "id": "timeline.place",
                "params": {"item": name_to_id[p.name], "track": "V2", "frame": f0, "video": True, "audio": False},
            })

        for sec_t, label, col in markers:
            steps.append({
                "id": "markers.add",
                "params": {"target": "program", "time": int(round(sec_t * TICKS_PER_SEC)), "name": label, "color": col},
            })
        if args.normalize_db is not None and has_audio:
            steps.append({"id": "sequence.normalizeMixTrack", "params": {"db": float(args.normalize_db)}})

        edit_jsonl = tmp / "fc_assemble.jsonl"
        edit_jsonl.write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")
        run_fc(["--project", str(out_fcproj), "--save", "run", str(edit_jsonl)], args.low_load, args.threads, args.cores)
        print(f"Saved FilmCraft project: {out_fcproj}")

        # 4. Export Master (V2 enabled)
        if args.export_master:
            out_m = args.export_master.resolve()
            out_m.parent.mkdir(parents=True, exist_ok=True)
            print(f"Exporting Master MP4 -> {out_m}")
            run_fc(["--project", str(out_fcproj), "export", str(out_m), "--preset", args.preset], args.low_load, args.threads, args.cores)
            if args.low_load and args.export_clean:
                time.sleep(3)

        # 5. Export Clean (V2 disabled, keeping all diegetic V1 text)
        if args.export_clean:
            if has_v2:
                off_jsonl = tmp / "fc_v2_off.jsonl"
                off_jsonl.write_text(
                    json.dumps({"id": "timeline.setTrack", "params": {"track": "V2", "enabled": False}}) + "\n",
                    encoding="utf-8",
                )
                run_fc(["--project", str(out_fcproj), "--save", "run", str(off_jsonl)], args.low_load, args.threads, args.cores)

            out_c = args.export_clean.resolve()
            out_c.parent.mkdir(parents=True, exist_ok=True)
            print(f"Exporting Clean MP4 -> {out_c}")
            run_fc(["--project", str(out_fcproj), "export", str(out_c), "--preset", args.preset], args.low_load, args.threads, args.cores)

            if has_v2:
                on_jsonl = tmp / "fc_v2_on.jsonl"
                on_jsonl.write_text(
                    json.dumps({"id": "timeline.setTrack", "params": {"track": "V2", "enabled": True}}) + "\n",
                    encoding="utf-8",
                )
                run_fc(["--project", str(out_fcproj), "--save", "run", str(on_jsonl)], args.low_load, args.threads, args.cores)

    print("FILMCRAFT_ASSEMBLY_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
