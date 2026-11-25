"""Shorten a short video (2-3 min) to a target length by keeping its best parts.

Two steps, with Claude choosing in between:

  analyze  probe the video, transcribe the speech, detect silences and scene
           cuts, measure loudness, and write candidate segments plus
           contact sheets for Claude to read.
  render   cut the segments listed in selection.json and join them.

Usage:
  python video_highlight.py analyze <video> --out <dir> [--model medium] [--lang ja]
  python video_highlight.py render <video> --out <dir> [--selection <json>] [--target 60]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SR = 16000            # sample rate for analysis audio
FRAME = 0.5           # seconds per loudness frame
MAX_SEG = 8.0         # split long silent/visual spans into pieces of this length
PAD = 0.15            # seconds added around each kept segment when cutting
FADE = 0.04           # audio fade at each cut, to avoid clicks


# ---------------------------------------------------------------- helpers

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def need(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"error: {tool} not found on PATH")


def probe(video: Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(video)])
    if r.returncode != 0:
        sys.exit(f"error: ffprobe failed: {r.stderr.strip()}")
    info = json.loads(r.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = 30.0
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 30.0
    return {
        "duration": float(info["format"]["duration"]),
        "has_video": v is not None,
        "has_audio": a is not None,
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "fps": round(fps, 3),
    }


def fmt(t: float) -> str:
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m)}:{s:04.1f}"


# ---------------------------------------------------------------- analyze

def load_audio(video: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn",
                        "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def loudness(audio: np.ndarray, duration: float) -> np.ndarray:
    """RMS level in dBFS per FRAME seconds."""
    n = int(math.ceil(duration / FRAME))
    hop = int(SR * FRAME)
    out = np.full(n, -90.0)
    for i in range(n):
        chunk = audio[i * hop:(i + 1) * hop]
        if chunk.size:
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            out[i] = 20 * math.log10(rms) if rms > 1e-9 else -90.0
    return out


def silences(audio: np.ndarray, level: np.ndarray, min_len: float = 0.4) -> list[tuple[float, float]]:
    """Silent spans: frames more than 25 dB below the loud end (95th pct)."""
    if level.size == 0 or audio.size == 0:
        return []
    thr = max(np.percentile(level, 95) - 25, -60)
    quiet = level < thr
    spans, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        if not q and start is not None:
            spans.append((start * FRAME, i * FRAME))
            start = None
    if start is not None:
        spans.append((start * FRAME, len(quiet) * FRAME))
    return [(a, b) for a, b in spans if b - a >= min_len]


def scene_cuts(video: Path, thr: float = 0.1) -> list[float]:
    """0.1 catches slide changes in talks; 0.3 (the usual value) missed them."""
    r = run(["ffmpeg", "-hide_banner", "-i", str(video), "-an",
             "-vf", f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"])
    cuts = []
    for line in r.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            try:
                cuts.append(round(float(line.split("pts_time:")[1].split()[0]), 2))
            except ValueError:
                pass
    return cuts


def add_cuda_dlls() -> None:
    """On Windows, let ctranslate2 find cuBLAS/cuDNN installed as pip wheels
    (python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12)."""
    if os.name != "nt":
        return
    import importlib.util
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        for base in (spec.submodule_search_locations or []) if spec else []:
            d = os.path.join(base, "bin")
            if os.path.isdir(d):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def transcribe(audio: np.ndarray, model: str, lang: str | None) -> tuple[list[dict], str]:
    if audio.size == 0:
        return [], "no audio"
    add_cuda_dlls()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return [], "faster-whisper not installed (python -m pip install faster-whisper)"
    last = ""
    for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
        try:
            m = WhisperModel(model, device=device, compute_type=ctype)
            segs, info = m.transcribe(audio, language=lang, vad_filter=True,
                                      word_timestamps=False, beam_size=5)
            out = [{"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": s.text.strip(), "no_speech": round(s.no_speech_prob, 2)}
                   for s in segs]
            return out, f"{model} on {device} (language: {info.language})"
        except Exception as e:  # CUDA libraries missing etc. -> fall back to CPU
            last = f"{device}: {e}"
            print(f"  {device} failed, trying next: {str(e)[:120]}", flush=True)
    return [], f"transcription failed ({last})"


def build_segments(duration: float, speech: list[dict], cuts: list[float],
                   level: np.ndarray) -> list[dict]:
    """Candidate units: speech segments, plus the gaps between them split at
    scene cuts and at MAX_SEG seconds."""
    spans: list[tuple[float, float, str, str]] = []
    t = 0.0
    for s in speech:
        if s["start"] - t > 0.3:
            spans.append((t, s["start"], "", "gap"))
        spans.append((s["start"], s["end"], s["text"], "speech"))
        t = max(t, s["end"])
    if duration - t > 0.3:
        spans.append((t, duration, "", "gap"))

    pieces = []
    for a, b, text, kind in spans:
        if kind == "speech":
            pieces.append((a, b, text, kind))
            continue
        bounds = [a] + [c for c in cuts if a + 1.0 < c < b - 1.0] + [b]
        for x, y in zip(bounds, bounds[1:]):
            n = max(1, int(math.ceil((y - x) / MAX_SEG)))
            step = (y - x) / n
            for k in range(n):
                pieces.append((x + k * step, x + (k + 1) * step, "", kind))

    segs = []
    for i, (a, b, text, kind) in enumerate(pieces, 1):
        lo, hi = int(a / FRAME), max(int(a / FRAME) + 1, int(math.ceil(b / FRAME)))
        lv = level[lo:hi] if level.size else np.array([-90.0])
        segs.append({
            "id": i, "start": round(a, 2), "end": round(b, 2),
            "dur": round(b - a, 2), "kind": kind, "text": text,
            "db": round(float(np.mean(lv)), 1) if lv.size else -90.0,
            "scene_cut": any(a - 0.25 <= c <= b for c in cuts),
        })
    return segs


def contact_sheets(video: Path, out: Path, duration: float, step: float) -> list[Path]:
    """One thumbnail per `step` seconds, 5 x 4 per sheet, labelled with time."""
    from PIL import Image, ImageDraw, ImageFont
    tmp = Path(tempfile.mkdtemp(prefix="vh_frames_"))   # outside the work dir: sync tools (Dropbox etc.) lock files there
    run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
         f"fps=1/{step},scale=320:-2", str(tmp / "f%04d.jpg")])
    frames = sorted(tmp.glob("f*.jpg"))
    if not frames:
        return []
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    cols, rows = 5, 4
    with Image.open(frames[0]) as im:
        w, h = im.size
    sheets = []
    for si in range(0, len(frames), cols * rows):
        sheet = Image.new("RGB", (cols * w, rows * (h + 24)), "white")
        d = ImageDraw.Draw(sheet)
        for k, f in enumerate(frames[si:si + cols * rows]):
            x, y = (k % cols) * w, (k // cols) * (h + 24)
            with Image.open(f) as im:
                sheet.paste(im, (x, y + 24))
            d.text((x + 4, y + 2), fmt((si + k) * step + step / 2), fill="black", font=font)
        p = out / f"sheet_{si // (cols * rows) + 1:02d}.jpg"
        sheet.save(p, quality=85)
        sheets.append(p)
    shutil.rmtree(tmp, ignore_errors=True)
    return sheets


def cmd_analyze(a: argparse.Namespace) -> None:
    need("ffmpeg"); need("ffprobe")
    video, out = Path(a.video), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    dur = info["duration"]
    print(f"probe: {fmt(dur)} {info['width']}x{info['height']} {info['fps']} fps "
          f"audio={info['has_audio']}", flush=True)

    audio = load_audio(video) if info["has_audio"] else np.zeros(0, np.float32)
    level = loudness(audio, dur) if audio.size else np.zeros(0)
    sil = silences(audio, level)
    cuts = scene_cuts(video, a.scene) if info["has_video"] else []
    print(f"silences: {len(sil)}  scene cuts: {len(cuts)}", flush=True)

    cache = out / "transcript.json"
    if a.no_transcribe:
        speech, note = [], "skipped (--no-transcribe)"
    elif cache.exists() and not a.retranscribe:
        c = json.loads(cache.read_text(encoding="utf-8"))
        speech, note = c["speech"], c["note"] + " (cached; --retranscribe to redo)"
    else:
        speech, note = transcribe(audio, a.model, a.lang)
        if speech:
            cache.write_text(json.dumps({"note": note, "speech": speech},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"transcribe: {note}, {len(speech)} segments", flush=True)

    segs = build_segments(dur, speech, cuts, level)
    step = a.sheet_step or max(1.0, round(dur / 60, 1))
    sheets = contact_sheets(video, out, dur, step) if info["has_video"] else []

    data = {"video": str(video.resolve()), "info": info, "transcriber": note,
            "silences": sil, "scene_cuts": cuts, "segments": segs,
            "sheet_step": step, "sheets": [p.name for p in sheets]}
    (out / "segments.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                       encoding="utf-8")

    speech_dur = sum(s["dur"] for s in segs if s["kind"] == "speech")
    lines = [f"# {video.name}", "",
             f"- length {fmt(dur)} ({dur:.1f} s), {info['width']}x{info['height']}, audio={info['has_audio']}",
             f"- speech {speech_dur:.1f} s in {sum(s['kind'] == 'speech' for s in segs)} segments; transcriber: {note}",
             f"- scene cuts at: {', '.join(fmt(c) for c in cuts) or 'none'}",
             f"- contact sheets: {', '.join(p.name for p in sheets) or 'none'} (one frame per {step} s, label = time)",
             "", "| id | start | end | dur | kind | dB | cut | text |",
             "|---:|---:|---:|---:|---|---:|:-:|---|"]
    for s in segs:
        lines.append(f"| {s['id']} | {fmt(s['start'])} | {fmt(s['end'])} | {s['dur']:.1f} | "
                     f"{s['kind']} | {s['db']:.0f} | {'*' if s['scene_cut'] else ''} | "
                     f"{s['text'].replace('|', '/')} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out / 'summary.md'}, {out / 'segments.json'}, {len(sheets)} sheets")


# ---------------------------------------------------------------- render

def snap(t: float, sil: list[list[float]], is_start: bool) -> float:
    """Move a cut point into a nearby silence, so words are not clipped.
    Keeps 0.25 s of the silence next to the kept side."""
    for a, b in sil:
        if is_start and a <= t <= b + 0.6:      # silence covers t or ends just before it
            return max(a, b - 0.25)
        if not is_start and a - 0.6 <= t <= b:  # silence covers t or starts just after it
            return min(b, a + 0.25)
    return max(0.0, t - PAD) if is_start else t + PAD


def resolve(selection: dict, segs: dict[int, dict], dur: float,
            sil: list[list[float]]) -> list[tuple[float, float]]:
    spans = []
    for item in selection["keep"]:
        if isinstance(item, int):
            s = segs[item]; spans.append((s["start"], s["end"]))
        elif "id" in item:
            s = segs[item["id"]]
            spans.append((item.get("start", s["start"]), item.get("end", s["end"])))
        else:
            spans.append((float(item["start"]), float(item["end"])))
    spans.sort()
    merged: list[list[float]] = []
    for a, b in spans:
        a, b = snap(a, sil, True), min(dur, snap(b, sil, False))
        if merged and a <= merged[-1][1] + 0.3:     # join touching pieces
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a > 0.2]


def cmd_render(a: argparse.Namespace) -> None:
    need("ffmpeg"); need("ffprobe")
    out = Path(a.out)
    data = json.loads((out / "segments.json").read_text(encoding="utf-8"))
    video = Path(a.video or data["video"])
    info = data["info"]
    sel_path = Path(a.selection) if a.selection else out / "selection.json"
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    spans = resolve(sel, {s["id"]: s for s in data["segments"]}, info["duration"],
                    data.get("silences", []))
    total = sum(b - a for a, b in spans)
    target = a.target or sel.get("target")
    print(f"{len(spans)} pieces, total {total:.1f} s" +
          (f" (target {target} s, diff {total - target:+.1f} s)" if target else ""))
    if target and abs(total - target) > max(2.0, 0.05 * target):
        print("warning: total is off the target by more than 5% (or 2 s)")

    parts = Path(tempfile.mkdtemp(prefix="vh_parts_"))   # outside the work dir (see above)
    listing = []
    for i, (s, e) in enumerate(spans, 1):
        d = e - s
        p = parts / f"p{i:03d}.mp4"
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-t", f"{d:.3f}",
               "-i", str(video)]
        if info["has_video"]:
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", str(a.crf),
                    "-pix_fmt", "yuv420p", "-r", str(info["fps"])]
        else:
            cmd += ["-vn"]
        if info["has_audio"]:
            f = min(FADE, d / 4)
            cmd += ["-af", f"afade=t=in:d={f:.3f},afade=t=out:st={d - f:.3f}:d={f:.3f}",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        else:
            cmd += ["-an"]
        cmd += [str(p)]
        r = run(cmd)
        if r.returncode != 0:
            sys.exit(f"error: cutting piece {i} failed: {r.stderr.strip()}")
        listing.append(f"file '{p.resolve().as_posix()}'")
        print(f"  piece {i}: {fmt(s)}-{fmt(e)} ({d:.1f} s)", flush=True)
    (parts / "list.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")

    dst = out / (a.name or f"{video.stem}_{int(round(target or total))}s.mp4")
    r = run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(parts / "list.txt"), "-c", "copy", "-movflags", "+faststart", str(dst)])
    if r.returncode != 0:
        sys.exit(f"error: joining failed: {r.stderr.strip()}")
    shutil.rmtree(parts, ignore_errors=True)
    got = probe(dst)["duration"]
    print(f"wrote {dst} ({got:.1f} s)")


def cmd_check(a: argparse.Namespace) -> None:
    """Transcribe the finished video so cut words or broken sentences show up."""
    need("ffmpeg"); need("ffprobe")
    video = Path(a.video)
    info = probe(video)
    print(f"{video.name}: {info['duration']:.1f} s")
    speech, note = transcribe(load_audio(video), a.model, a.lang)
    print(f"transcribe: {note}")
    for s in speech:
        print(f"  {fmt(s['start'])}-{fmt(s['end'])}  {s['text']}")


# ---------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("analyze", help="transcribe and segment the video")
    q.add_argument("video")
    q.add_argument("--out", required=True, help="working directory for outputs")
    q.add_argument("--model", default="medium", help="faster-whisper model (default: medium)")
    q.add_argument("--lang", default="ja", help="speech language; 'auto' to detect (default: ja)")
    q.add_argument("--no-transcribe", action="store_true", help="skip speech recognition")
    q.add_argument("--retranscribe", action="store_true", help="ignore <out>/transcript.json")
    q.add_argument("--scene", type=float, default=0.1,
                   help="scene-change threshold 0-1; lower finds more cuts (default: 0.1)")
    q.add_argument("--sheet-step", type=float, default=0, help="seconds per thumbnail (default: length/60)")
    q.set_defaults(func=cmd_analyze)

    r = sub.add_parser("render", help="cut and join the selected segments")
    r.add_argument("video", nargs="?", help="source video (default: the one analyzed)")
    r.add_argument("--out", required=True, help="the same directory given to analyze")
    r.add_argument("--selection", help="selection JSON (default: <out>/selection.json)")
    r.add_argument("--target", type=float, help="target length in seconds, for the check")
    r.add_argument("--name", help="output file name (default: <stem>_<target>s.mp4)")
    r.add_argument("--crf", type=int, default=20, help="x264 quality (default: 20)")
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("check", help="transcribe the finished video to check the cuts")
    c.add_argument("video")
    c.add_argument("--model", default="medium")
    c.add_argument("--lang", default="ja")
    c.set_defaults(func=cmd_check)

    a = p.parse_args()
    if getattr(a, "lang", None) == "auto":
        a.lang = None
    a.func(a)


if __name__ == "__main__":
    main()
