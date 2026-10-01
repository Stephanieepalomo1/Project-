#!/usr/bin/env python3
"""audio_levels.py — the ONE place that decides how loud a sound effect or a music bed is.

SHARED BASE MODULE. Every format calls this (baked well-done, CapCut Clean/Super Yap, Voiceover). A level
fix lands here once and every lane gets it in the same change; never hand-tune a number in a format.

## The rule: never express a cue's level as a bare offset or a bare multiplier

A number like `gain_db: -12` or `volume: 1.0` says nothing about how loud a cue will actually SOUND, because
it is applied to whatever level that particular file happens to have. The bundled SFX span about 20 dB of
intrinsic level:

    pop.mp3              -17.4 dBFS rms  (loudest)
    keyboard_typing.mp3  -37.6 dBFS rms  (quietest)

So one shared number makes `pop` land 20 dB hotter than `keyboard_typing`. At the old `-12` default, seven
of the nine bundled SFX landed INAUDIBLE and two were marginal. Zero landed right.

Worse, it fails SILENTLY. Nothing errors; the reel simply ships with no sound design. On the Hands-Off lane
there is no human review step at all, so nobody would ever catch it. (Found by ear on a finished reel whose
cues measured +0.04 dB against the mix and had shipped as "done". Locked.)

## What this module does instead

MEASURE the cue, MEASURE the programme, and place the cue a fixed distance under it. Then every cue lands
at the same perceived level whichever file was chosen.

  * SFX are transients -> matched by PEAK, `programme_peak + SFX_DUCK_DB`.
  * A music bed is continuous -> matched by MEAN, `programme_mean + BED_DUCK_DB`.
  * With no programme reference available, cues still normalise to a canonical target, which on its own
    removes the 20 dB spread.

An explicit level from the caller always still wins, for deliberate hand-tuning.

ALWAYS print `report(...)` from a build. A level you have not seen printed is a level nobody has checked,
and that is exactly how this shipped broken the first time.

Levels here are MEASURED, never heard. The creator is the ear on whether a cue finally sits right.
"""
import os, re, subprocess

SFX_DUCK_DB = -6.0          # an SFX peak sits this far under the programme peak
BED_DUCK_DB = -15.0         # a music bed's mean sits this far under the programme mean
SFX_TARGET_PEAK_DBFS = -7.0 # canonical SFX peak when no programme reference is available
BED_TARGET_MEAN_DBFS = -30.0
GAIN_MIN_DB, GAIN_MAX_DB = -40.0, 12.0   # a computed gain outside this means a bad measurement, not intent


def _volumedetect(path, field, trim=None):
    if not path or not os.path.exists(path):
        return None
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-i", path]
    if trim:
        cmd += ["-t", f"{float(trim):.3f}"]
    cmd += ["-af", "volumedetect", "-f", "null", os.devnull]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stderr
    except Exception:
        return None
    m = re.search(rf"{field}:\s*(-?[\d.]+) dB", out)
    return float(m.group(1)) if m else None


def peak_dbfs(path, trim=None):
    """True peak in dBFS — the honest measure for a short transient (an SFX cue)."""
    return _volumedetect(path, "max_volume", trim)


def mean_dbfs(path, trim=None):
    """Average level in dBFS — the honest measure for a continuous signal (a music bed, a voice track)."""
    return _volumedetect(path, "mean_volume", trim)


def _clamp(db):
    return max(GAIN_MIN_DB, min(GAIN_MAX_DB, db))


def sfx_gain_db(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """dB of gain to apply to an SFX file so its peak lands duck_db under the programme peak.
    With no programme reference, normalises to SFX_TARGET_PEAK_DBFS, which alone kills the 20 dB spread."""
    src = peak_dbfs(sfx_path, trim)
    if src is None:
        return 0.0
    target = (programme_peak_db + duck_db) if programme_peak_db is not None else SFX_TARGET_PEAK_DBFS
    return _clamp(target - src)


def bed_gain_db(bed_path, programme_mean_db=None, duck_db=BED_DUCK_DB):
    """dB of gain for a music bed so its mean sits duck_db under the programme mean."""
    src = mean_dbfs(bed_path)
    if src is None:
        return 0.0
    target = (programme_mean_db + duck_db) if programme_mean_db is not None else BED_TARGET_MEAN_DBFS
    return _clamp(target - src)


def sfx_landing(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """(gain_db, lands_dbfs, clamped) for a cue. `clamped` = the file is too quiet to reach target within
    GAIN_MAX_DB, so it lands short. That is deliberate — boosting a very quiet file to target would drag its
    noise floor up with it — but it must be REPORTED, never silently accepted."""
    src = peak_dbfs(sfx_path, trim)
    if src is None:
        return 0.0, None, False
    target = (programme_peak_db + duck_db) if programme_peak_db is not None else SFX_TARGET_PEAK_DBFS
    want = target - src
    gain = _clamp(want)
    return gain, src + gain, abs(want - gain) > 0.05


def to_linear(gain_db, lo=0.02, hi=4.0):
    """dB -> the linear multiplier CapCut / VectCutAPI want in a segment's `volume` field."""
    return round(max(lo, min(hi, 10 ** (float(gain_db) / 20.0))), 4)


def sfx_volume(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """Linear volume multiplier for an SFX in an editor timeline (CapCut lanes)."""
    return to_linear(sfx_gain_db(sfx_path, programme_peak_db, duck_db, trim))


def bed_volume(bed_path, programme_mean_db=None, duck_db=BED_DUCK_DB):
    """Linear volume multiplier for a music bed in an editor timeline."""
    return to_linear(bed_gain_db(bed_path, programme_mean_db, duck_db))


def report(rows, programme_peak_db=None, programme_mean_db=None, prefix="[levels]"):
    """Print what was computed. Never ship a level nobody has seen — silent failure is the whole bug."""
    if programme_peak_db is not None or programme_mean_db is not None:
        bits = []
        if programme_peak_db is not None:
            bits.append(f"peak {programme_peak_db:.1f} dBFS")
        if programme_mean_db is not None:
            bits.append(f"mean {programme_mean_db:.1f} dBFS")
        print(f"{prefix} programme {' · '.join(bits)}")
    for r in rows:
        name = os.path.basename(str(r.get("file", "?")))
        gain = r.get("gain_db", 0.0)
        lands = r.get("lands_dbfs")
        how = r.get("how", "auto")
        tail = f" -> {lands:6.1f} dBFS" if lands is not None else ""
        warn = "  ⚠ too quiet to reach target (boosting further would raise its noise floor)" if r.get("clamped") else ""
        print(f"{prefix}   {name:24} gain {gain:+6.1f} dB ({how}){tail}{warn}")
