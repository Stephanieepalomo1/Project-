#!/usr/bin/env python3
"""Transcribe with faster-whisper ONLY (no torch, no whisperx) and write the engine's words.json.

This is the Intel-Mac path: PyTorch's last macOS x86_64 wheel is 2.2.2, and WhisperX now needs
torch~=2.8, so the whisperx venv cannot be built on an Intel Mac at all. faster-whisper rides on
CTranslate2, which still ships Intel-Mac wheels, and it carries its own word timestamps.

Trade-off vs. the whisperx path: no wav2vec2 alignment pass, so word times come from Whisper's own
cross-attention. Slightly looser edges, same JSON shape, ~175 MB of deps instead of ~3 GB.

Usage: python transcribe-nofw.py <out.json> <clip> [clip ...]
"""
import json, os, platform, sys, time

from faster_whisper import WhisperModel

out_path = sys.argv[1]
clip_paths = sys.argv[2:]

# Model choice. The whisperx path decides this with `os.cpu_count() <= 4`, which counts LOGICAL
# cores — and that misreads the exact machine this file exists for. A 1.4 GHz quad-core i5 (the 2019
# 13" MacBook Pro, our first confirmed Intel buyer) has hyperthreading, so os.cpu_count() reports 8,
# the "weak" test comes back False, and she gets `medium` on a chip that cannot carry it.
#
# Count PHYSICAL cores here, and treat a true Intel Mac as weak by default regardless: there is no
# Apple Silicon int8 acceleration on this path, so the ceiling is low whatever the core count says.
# REELS_ENGINE_WHISPER_MODEL still overrides, for anyone who would rather wait for full quality.
def _physical_cores():
    try:
        import subprocess
        out = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return int(out)
    except Exception:
        return 0

cpu_count = os.cpu_count() or 4
physical = _physical_cores() or cpu_count
is_intel_mac = (sys.platform == "darwin" and platform.machine() not in ("arm64", "aarch64"))
is_weak_cpu = is_intel_mac or physical <= 4

model_name = os.environ.get("REELS_ENGINE_WHISPER_MODEL", "").strip() or (
    "small" if is_weak_cpu else "medium")

print(f"[transcribe] loading faster-whisper {model_name} (cpu, int8, {physical} cores / "
      f"{cpu_count} threads)",
      file=sys.stderr)
model = WhisperModel(model_name, device="cpu", compute_type="int8")

_t_start = time.monotonic()
total_clip_seconds = 0.0

result = {"clips": []}
for path in clip_paths:
    name = os.path.basename(path)
    print(f"[transcribe] {name}", file=sys.stderr)
    # This line used to pin language="en". It was copied from the WhisperX path without questioning
    # it, and it is the wrong default on the one route most likely to carry non-English footage.
    # faster-whisper decides per SEGMENT under multilingual=True rather than once per file, which is
    # what a code-switching reel actually needs: auto-detect alone locks the whole clip to the
    # dominant language and renders the other half as a fluent paraphrase of what was meant instead
    # of what was said. Older builds lack the argument, hence the fallback.
    try:
        segments, info = model.transcribe(path, language=None, multilingual=True,
                                          word_timestamps=True, vad_filter=True)
    except TypeError:
        segments, info = model.transcribe(path, language=None,
                                          word_timestamps=True, vad_filter=True)

    words = []
    seg_languages = {}
    for seg in segments:
        _sl = getattr(seg, "language", None) or getattr(info, "language", None)
        if _sl:
            seg_languages[_sl] = seg_languages.get(_sl, 0) + 1
        for w in (seg.words or []):
            if w.start is None or w.end is None:
                continue
            words.append({
                "w": str(w.word).strip(),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "prob": round(float(getattr(w, "probability", 1.0)), 3),
            })

    total_clip_seconds += float(info.duration)

    result["clips"].append({
        "clip": name,
        "path": path,
        "duration": round(float(info.duration), 3),
        # What was actually DETECTED, per segment. Nothing recorded a language before this, which is
        # how a Spanish reel reached the end of the pipeline labelled English without anyone noticing.
        "languages": dict(sorted(seg_languages.items(), key=lambda kv: -kv[1])),
        "words": words,
    })

# encoding is explicit on purpose: Windows text mode defaults to cp1252, which cannot represent an
# accented word and would corrupt the transcript of anyone not speaking plain English.
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)
print(f"[transcribe] wrote {out_path}", file=sys.stderr)

# Diagnostics, in the SAME file and shape the whisperx path writes, so
# `python3 product/make-handoff.py hardware-diagnostic` picks this route up with no changes of its
# own. This is the only way we ever learn what an Intel Mac actually costs per minute of footage:
# there is no Intel machine on this side to measure, so the number has to come home from a real one.
# Best-effort throughout — diagnostics never fail a real transcription.
wall_seconds = round(time.monotonic() - _t_start, 1)
diag_path = os.path.join(os.path.dirname(out_path), ".transcribe-diagnostics.json")
try:
    all_scores = [w["prob"] for c in result["clips"] for w in c["words"]]
    avg_confidence = round(sum(all_scores) / len(all_scores), 3) if all_scores else None
    diag = {
        "engine": "faster-whisper",   # the whisperx path writes no such key — that is how they are told apart
        "engine_reason": "no torch on this machine (Intel Mac, or torch unavailable)",
        "device": "cpu", "model": model_name, "compute_type": "int8",
        "cpu_logical_cores": cpu_count,
        "cpu_physical_cores": physical,
        "is_apple_silicon": not is_intel_mac,
        "is_weak_cpu": is_weak_cpu,
        "platform": sys.platform, "machine": platform.machine(),
        "wall_seconds": wall_seconds,
        "total_clip_seconds": round(total_clip_seconds, 1),
        "realtime_ratio": round(wall_seconds / total_clip_seconds, 2) if total_clip_seconds > 0 else None,
        "avg_word_confidence": avg_confidence,
    }
    os.makedirs(os.path.dirname(diag_path) or ".", exist_ok=True)
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2)
except Exception:
    pass
