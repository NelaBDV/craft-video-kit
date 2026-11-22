#!/usr/bin/env python3
"""
audio_cues.py — Precision 44.1 kHz audio inspection, ear-verification slicing,
and editable `lyrics_timing.json` scaffolding for music video production.

Key design lessons baked in:
  - Always decodes to 44100 Hz mono PCM so `hop = 441` samples == exact 10.000 ms
    (avoids cumulative timing drift caused by rounded hops at 22050 Hz).
  - Measures exact duration, ending transients, and reverb/silence tail directly on
    the master audio file before locking edit duration or final black cuts.
  - Cuts overlapping listening slices and tight boundary clips so an agent or editor
    can verify BPM, chorus entries, choir echoes, and endings by ear.

Dependencies: Python 3.9+ (standard library only), ffmpeg, ffprobe.
"""

import argparse
import json
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SAMPLE_RATE = 44100
HOP_10MS = 441  # Exact 0.010000 s at 44100 Hz (zero drift!)


def probe_audio(audio_path: Path) -> Dict:
    """Read exact duration, sample rate, codec, and channels via ffprobe."""
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,size,bit_rate",
            "-show_entries", "stream=codec_name,sample_rate,channels",
            "-of", "json", str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(res.stdout)
    fmt = data.get("format", {})
    streams = [s for s in data.get("streams", []) if s.get("sample_rate")]
    st = streams[0] if streams else {}
    return {
        "file": str(audio_path),
        "duration_s": round(float(fmt.get("duration", 0.0)), 4),
        "duration_ms": int(round(float(fmt.get("duration", 0.0)) * 1000.0)),
        "codec": st.get("codec_name", "unknown"),
        "sample_rate": int(st.get("sample_rate", 0)),
        "channels": int(st.get("channels", 0)),
    }


def decode_mono_44k(audio_path: Path) -> Tuple[List[int], float]:
    """Decode any audio file to 44100 Hz 16-bit mono PCM in a temporary WAV."""
    with tempfile.TemporaryDirectory(prefix="craft_audio_") as td:
        wav_path = Path(td) / "mono_44k.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-threads", "2",
                "-i", str(audio_path),
                "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            assert sr == SAMPLE_RATE, f"Expected {SAMPLE_RATE} Hz, got {sr}"
            n = wf.getnframes()
            raw = wf.readframes(n)
    samples = list(struct.unpack("<" + "h" * n, raw))
    return samples, n / float(SAMPLE_RATE)


def compute_10ms_envelope(samples: List[int]) -> Tuple[List[float], List[float]]:
    """Compute exact 10 ms RMS (0..1) and positive onset flux (0..1)."""
    rms: List[float] = []
    n = len(samples)
    for i in range(0, n - HOP_10MS + 1, HOP_10MS):
        seg = samples[i:i + HOP_10MS]
        rms.append(math.sqrt(sum(s * s for s in seg) / HOP_10MS) / 32768.0)
    flux = [0.0] + [max(0.0, rms[i] - rms[i - 1]) for i in range(1, len(rms))]
    return rms, flux


def detect_transients(
    flux: List[float],
    min_flux: float = 0.08,
    min_gap_s: float = 0.14,
) -> List[Dict]:
    """Pick local onset peaks at 10 ms resolution."""
    peaks: List[Dict] = []
    max_f = max(flux) or 1.0
    for i in range(2, len(flux) - 2):
        val = flux[i]
        if val >= min_flux and val == max(flux[i - 2:i + 3]):
            t_s = round(i * 0.01, 3)
            if not peaks or (t_s - peaks[-1]["t_s"]) >= min_gap_s:
                peaks.append({
                    "t_s": t_s,
                    "t_ms": int(round(t_s * 1000)),
                    "strength": round(min(1.0, val / max_f), 3),
                })
    return peaks


def inspect_tail(rms: List[float], flux: List[float], tail_window_s: float = 12.0) -> Dict:
    """Summarize final accents, last strong hit, and decay to silence at track end."""
    total_steps = len(rms)
    start_idx = max(0, total_steps - int(tail_window_s * 100))
    tail_peaks = [
        {"t_s": round(i * 0.01, 2), "rms": round(rms[i], 4), "flux": round(flux[i], 4)}
        for i in range(max(2, start_idx), total_steps - 2)
        if flux[i] >= 0.04 and flux[i] == max(flux[i - 2:i + 3])
    ]
    # Last index above -48 dBFS (~0.004)
    last_audible = 0
    for i in range(total_steps - 1, -1, -1):
        if rms[i] > 0.004:
            last_audible = i
            break
    return {
        "tail_window_start_s": round(start_idx * 0.01, 2),
        "last_audible_s": round(last_audible * 0.01, 2),
        "tail_peaks": tail_peaks[-15:],
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    audio_path = Path(args.audio).resolve()
    info = probe_audio(audio_path)
    samples, pcm_dur = decode_mono_44k(audio_path)
    rms, flux = compute_10ms_envelope(samples)
    peaks = detect_transients(flux, min_flux=args.min_flux, min_gap_s=args.min_gap)
    tail = inspect_tail(rms, flux, tail_window_s=args.tail_sec)

    result: Dict = {
        "meta": {
            **info,
            "pcm_duration_s": round(pcm_dur, 4),
            "analysis_sample_rate": SAMPLE_RATE,
            "hop_ms": 10.0,
        },
        "tail_inspection": tail,
        "transient_count": len(peaks),
        "transients": peaks,
    }

    if args.bpm:
        beat_period = 60.0 / float(args.bpm)
        beats = []
        bars = []
        t = float(args.first_beat)
        idx = 0
        while t <= pcm_dur:
            t_r = round(t, 4)
            beats.append(t_r)
            if idx % args.beats_per_bar == 0:
                bars.append({"bar": (idx // args.beats_per_bar) + 1, "t_s": t_r, "t_ms": int(round(t * 1000))})
            t += beat_period
            idx += 1
        result["grid"] = {
            "bpm": float(args.bpm),
            "first_beat_s": float(args.first_beat),
            "beat_period_s": round(beat_period, 6),
            "beats_per_bar": args.beats_per_bar,
            "bar_count": len(bars),
            "bars": bars,
        }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote audio analysis -> {out_path}")
    else:
        # Print concise terminal summary
        print(f"Audio: {audio_path.name} | dur={info['duration_s']:.3f}s ({info['duration_ms']} ms) | {info['codec']} {info['sample_rate']}Hz {info['channels']}ch")
        print(f"Transients detected: {len(peaks)} (min_flux={args.min_flux})")
        print(f"Tail last audible: {tail['last_audible_s']:.2f}s | Recent tail peaks:")
        for tp in tail["tail_peaks"][-8:]:
            print(f"  t={tp['t_s']:7.2f}s  rms={tp['rms']:.4f}  flux={tp['flux']:.4f}")
        if "grid" in result:
            g = result["grid"]
            print(f"Beat grid: {g['bpm']} BPM from {g['first_beat_s']}s ({g['bar_count']} bars)")
    return 0


def cmd_slice(args: argparse.Namespace) -> int:
    audio_path = Path(args.audio).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe_audio(audio_path)
    dur = info["duration_s"]
    ext = args.format
    codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if ext == "mp3" else ["-c:a", "pcm_s16le"]

    created: List[Path] = []
    if args.cues:
        cues = [float(x.strip()) for x in args.cues.split(",") if x.strip()]
        half = args.window / 2.0
        for idx, cue_s in enumerate(cues, start=1):
            t0 = max(0.0, cue_s - half)
            t1 = min(dur, cue_s + half)
            seg_dur = max(0.2, t1 - t0)
            out_file = out_dir / f"cue_{idx:02d}_{cue_s:06.2f}s.{ext}"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-threads", "2",
                    "-ss", f"{t0:.3f}", "-t", f"{seg_dur:.3f}",
                    "-i", str(audio_path), *codec, str(out_file),
                ],
                check=True,
            )
            created.append(out_file)
    else:
        step = max(1.0, args.segment_sec - args.overlap_sec)
        t0 = 0.0
        idx = 1
        while t0 < dur - 0.1:
            seg_dur = min(args.segment_sec, dur - t0)
            t1 = t0 + seg_dur
            out_file = out_dir / f"slice_{idx:02d}_{t0:06.2f}_{t1:06.2f}.{ext}"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-threads", "2",
                    "-ss", f"{t0:.3f}", "-t", f"{seg_dur:.3f}",
                    "-i", str(audio_path), *codec, str(out_file),
                ],
                check=True,
            )
            created.append(out_file)
            if t1 >= dur - 0.05:
                break
            t0 += step
            idx += 1

    print(f"Created {len(created)} listening slice(s) in {out_dir}")
    for p in created:
        print(f"  {p}")
    return 0


def cmd_init_timing(args: argparse.Namespace) -> int:
    audio_path = Path(args.audio).resolve()
    info = probe_audio(audio_path)
    fps = float(args.fps)
    dur_ms = info["duration_ms"]
    total_frames = int(math.ceil((dur_ms / 1000.0) * fps))
    video_dur_ms = int(round((total_frames / fps) * 1000.0))

    sections = []
    if args.sections:
        for token in args.sections.split(","):
            parts = [p.strip() for p in token.split(":")]
            if len(parts) != 3:
                raise ValueError(f"Expected 'ID:start_ms:end_ms', got {token!r}")
            sections.append({
                "id": parts[0],
                "label": parts[0],
                "start_ms": int(parts[1]),
                "end_ms": int(parts[2]),
            })
    else:
        sections = [
            {"id": "S01_Intro", "label": "Intro", "start_ms": 0, "end_ms": min(15000, video_dur_ms)},
            {"id": "S02_Main", "label": "Main", "start_ms": min(15000, video_dur_ms), "end_ms": video_dur_ms},
        ]

    skeleton = {
        "_comment": (
            "Editable master timing file. Adjust start_ms, end_ms, display_end_ms, text, "
            "words, or layout. Mark uncertain vocal/echo cues with 'uncertain': true and 'review_note'."
        ),
        "meta": {
            "title": args.title or audio_path.stem,
            "audio_file": str(audio_path),
            "audio_duration_ms": dur_ms,
            "video_duration_ms": video_dur_ms,
            "fps": fps,
            "bpm": float(args.bpm),
            "first_drum_hit_ms": 0,
            "last_accent_ms": max(0, dur_ms - 1000),
            "black_cut_ms": dur_ms,
        },
        "sections": sections,
        "phrases": [
            {
                "id": "s01_p1",
                "section": sections[0]["id"],
                "type": "lead",
                "text": "Exemple de phrase principale",
                "start_ms": 1000,
                "end_ms": 3400,
                "display_end_ms": 3800,
                "layout": {"x": 960, "y": 120, "align": "center", "size": 58, "color": "cream", "anim": "slide_settle"},
                "words": [
                    {"text": "Exemple de", "start_ms": 1000, "end_ms": 2100},
                    {"text": "phrase principale", "start_ms": 2120, "end_ms": 3400, "accent": "amber"},
                ],
            },
            {
                "id": "s01_echo1",
                "section": sections[0]["id"],
                "type": "echo",
                "text": "Écho !",
                "start_ms": 3500,
                "end_ms": 4300,
                "display_end_ms": 4500,
                "uncertain": True,
                "review_note": "Verify choir/echo onset by ear (+/-100 ms).",
                "layout": {"x": 1680, "y": 215, "align": "right", "size": 46, "color": "amber_soft", "anim": "pop_snap"},
            },
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote editable timing scaffold -> {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="44.1 kHz audio analysis & ear-verification slicer.")
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="Analyze exact duration, 10 ms transients, tail, and optional BPM grid.")
    pa.add_argument("audio", help="Path to master audio file (MP3/WAV/FLAC).")
    pa.add_argument("--bpm", type=float, help="Optional tempo in BPM for bar/beat grid.")
    pa.add_argument("--first-beat", type=float, default=0.0, help="Time in seconds of Bar 1 Beat 1.")
    pa.add_argument("--beats-per-bar", type=int, default=4)
    pa.add_argument("--min-flux", type=float, default=0.08, help="Transient flux threshold (0..1).")
    pa.add_argument("--min-gap", type=float, default=0.14, help="Min gap between transients in seconds.")
    pa.add_argument("--tail-sec", type=float, default=12.0, help="Ending inspection window in seconds.")
    pa.add_argument("--out", help="Optional JSON output path.")
    pa.set_defaults(func=cmd_analyze)

    ps = sub.add_parser("slice", help="Extract overlapping listening slices or targeted cue clips.")
    ps.add_argument("audio", help="Path to master audio file.")
    ps.add_argument("--out-dir", required=True, help="Directory to write listening clips.")
    ps.add_argument("--segment-sec", type=float, default=18.0, help="Full-track slice duration (seconds).")
    ps.add_argument("--overlap-sec", type=float, default=2.0, help="Overlap between slices (seconds).")
    ps.add_argument("--cues", help="Comma-separated cue times in seconds (e.g. '32.1,47.8,174.4').")
    ps.add_argument("--window", type=float, default=3.0, help="Total window around each cue (seconds).")
    ps.add_argument("--format", choices=("mp3", "wav"), default="mp3")
    ps.set_defaults(func=cmd_slice)

    pt = sub.add_parser("init-timing", help="Create an editable lyrics_timing.json scaffold.")
    pt.add_argument("audio", help="Path to master audio file.")
    pt.add_argument("--out", required=True, help="Destination JSON path.")
    pt.add_argument("--title", help="Track title.")
    pt.add_argument("--bpm", type=float, default=120.0)
    pt.add_argument("--fps", type=float, default=30.0)
    pt.add_argument("--sections", help="Optional comma-separated 'ID:start_ms:end_ms' entries.")
    pt.set_defaults(func=cmd_init_timing)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
