#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-framework-ApplicationServices; sys_platform == 'darwin'",
#   "pyobjc-framework-Quartz; sys_platform == 'darwin'",
# ]
# ///
"""capcut-live.py — the engine's hands inside CapCut, which publishes no API of any kind.

There are exactly two ways in, and this script is both of them:

  ON DISK (the file lane). A CapCut draft is a folder of plain JSON in CapCut's drafts folder (under ~/Movies on a
      Mac, under %LOCALAPPDATA% on Windows). `replay` turns projects/<job>/transcript/cuts.json into a brand-new
      draft: the timeline JSON, draft_meta_info.json, and the registry row that puts the draft on CapCut's home
      screen. One timeline clip per cut, with source times in microseconds. `add-overlay`, `add-text`,
      `transform`, `remove` and `graphics` build on a draft that already exists. CapCut keeps its own copy of an
      open draft in memory and writes the files back from that copy when it quits, so anything written while it
      runs is silently thrown away. On a Mac every write here asks CapCut to quit first and brings it back after;
      on Windows a write refuses while CapCut is open, because the only close that fully ends it there is a
      forced kill, which loses whatever she had not saved. This lane works on Windows too. `--track` picks
      tracks by what they hold (main = the footage track, overlay = any other video track, text = text), since a
      draft built through VectCut carries the same flag on every track.

  IN THE RUNNING APP (the live lane). CapCut's interface is QML, and it hands its internal automation ids to the
      macOS accessibility tree: the playhead readout is currentProgress|HH:MM:SS:FF, each clip is
      MTLSVideoP:<clip>, the play button is PlayerPlayBtn, and so on. So an element can be looked up by id and
      clicked with a synthesized mouse event at the centre of where it really sits, and the app's own readouts can
      be read back to check the result. Those ids are CapCut's private test hooks, not a promise: after any CapCut
      update, re-map them with `dump` before trusting a live command. Mac only; on Windows a live command says so
      and the disk lane still works.

The ids were validated against CapCut 8.9.0. The file-lane half has worked on Windows for a while, and for a
time this header still said "macOS only"; both PC test runs believed it, skipped the bridge and hand-wrote a
per-reel build script instead. So this header says plainly what runs where.

USAGE below lists the everyday commands. Two maintenance ones, `magnet` and `verify-magnet`, are dispatched
too without being listed there (the capcut skill runs them after every build).

A live `export` or `open` straight after `magnet` used to fail ("can't find CapCut's Export button. Is a draft open?"):
  magnet relaunched CapCut onto its home screen and said it had reopened the draft. On a Mac it now opens the
  draft again itself. `open` matches the draft's title exactly, so "Reel 1.1" can no longer open "Reel 1.12".
  Separately: driving the screen takes over the buyer's real mouse and keyboard, and on a fresh-Mac test the
  buyer did not want that once she understood it. Whether automated export ships at all is an open product
  question, and it gates any work here.
"""
import sys as _sys, os as _os_ds
for _s in (_sys.stdout, _sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "../product"))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific

import json, os, shutil, subprocess, sys, time, uuid
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "product"))
from capcut_ripple import enforce_maintrack_ripple, snap_draft_dir, verify_draft_dir  # the ONE magnet anchor
import capcut_media  # owns the root_meta_info.json row, including a brand-new install's empty registry

USAGE = """capcut-live: CapCut has no API, so the engine works it from two sides.

Writing the draft on disk (CapCut is closed for the write and reopened after; on Windows, close it first):
  replay <job> [--name <draft>]          lay the job's cut list down as a new draft, one clip per cut
  add-overlay <draft> <mov> --at <s> [--dur <s>] [--layer N] [--force]
  add-text <draft> "<text>" --at <s> [--dur <s>] [--force]
  graphics <draft> <job>                 place every graphic the job's plan names, in one pass
  transform <draft> [--track main|text|overlay] [--index N], then any of: --x X --y Y --scale S --rotate R --opacity O
  remove <draft> [--track main|text|overlay] [--index N]
  ls                                     list the drafts CapCut knows about

Working the open editor (nothing restarts):
  launch · open <draft> · quit
  seek <seconds> [--draft <name>]        park on the exact frame, then read it back to be sure
  select <i> · delete <i> · split [seconds] · trim-left · trim-right
  undo · redo · save · marker · zoomfit · play
  playhead · clips · state               state prints the timeline as JSON
  export [--to <dir>] [--timeout <s>]    run the export dialog, then wait for the file to land
  shot [out.png]                         a picture of the CapCut window
  key <combo> · click <name> · clickxy <x> <y> · dump [needle]"""

APP_NAME = "CapCut"
ON_WINDOWS = os.name == "nt"
DRAFTS = ((Path(os.environ["LOCALAPPDATA"]) if ON_WINDOWS else Path.home() / "Movies")
          / "CapCut/User Data/Projects/com.lveditor.draft")
REPO = Path(__file__).resolve().parent.parent
TEXT_TEMPLATES = Path(__file__).resolve().parent / "capcut-shells"
POLL_SECONDS = 0.5


# ---------------------------------------------------------------------------------------------- the app itself

def tell_capcut(verb):
    """AppleScript's polite form: 'activate' brings CapCut forward, 'quit' asks it to save and close. A Mac has
    AppleScript and a PC does not, so on Windows this does nothing: calling osascript there crashed a draft edit
    that had already saved, on its way to reopening the draft."""
    if ON_WINDOWS:
        return
    subprocess.run(["osascript", "-e", f'tell application "{APP_NAME}" to {verb}'], check=False)


def capcut_pid():
    """CapCut's process id, or None when it is not running."""
    if ON_WINDOWS:
        return _pid_from_tasklist()
    try:
        listed = subprocess.check_output(["pgrep", "-x", APP_NAME])
    except subprocess.CalledProcessError:
        return None                                      # pgrep's own way of saying "no match"
    return int(listed.split()[0])


def _pid_from_tasklist():
    """tasklist rather than pgrep on Windows. CapCut runs as a main process plus helpers, so several rows can
    match and any one of them proves it is open. A tasklist that fails, or a row that will not parse, counts as
    'not running'."""
    try:
        rows = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                              capture_output=True, text=True).stdout.splitlines()
        return next((int(cols[1]) for cols in (row.split() for row in rows)
                     if len(cols) >= 2 and cols[0].lower().startswith("capcut")), None)
    except Exception:
        return None


def quit_capcut(timeout=20):
    """Close CapCut and wait until it is really gone. On Windows it is a forced kill of the whole process tree,
    because the helper processes outlive a polite close, so only the `quit` command she types herself uses it
    there. A draft write never does: see close_for_write."""
    if capcut_pid() is None:
        return
    if ON_WINDOWS:
        subprocess.run(["taskkill", "/IM", "CapCut.exe", "/F", "/T"], capture_output=True, check=False)
    else:
        tell_capcut("quit")
    asked = time.time()
    while capcut_pid() is not None:
        if time.time() - asked > timeout:
            sys.exit(f"CapCut was still running {timeout}s after being asked to quit. "
                     f"Close it by hand, then run this again.")
        time.sleep(POLL_SECONDS)


def start_capcut():
    if ON_WINDOWS:
        subprocess.run(["cmd", "/c", "start", "", "capcut:"], check=False)   # CapCut's URL scheme
        return
    subprocess.run(["open", "-a", APP_NAME], check=True)
    tell_capcut("activate")


def close_for_write(action):
    """Get CapCut out of the way of a draft write, or refuse the write.

    On a Mac it is asked to quit, which saves whatever she has open, and waited for. On Windows nothing is closed
    for her: the only close that reliably ends CapCut's helper processes there is a forced kill, and a forced kill
    throws away anything she had not saved yet, so the write is refused instead and she closes CapCut herself,
    exactly as the builders ask. Either way draft_safety has the last word before anything is written. It also
    catches a CapCut that `pgrep -x` alone does not see, and it counts "could not tell" as open."""
    if not ON_WINDOWS:
        quit_capcut()
    _ds.require_capcut_quit(action)


# ---------------------------------------------------------------------------------------------- reading the screen
# ApplicationServices and Quartz are macOS system frameworks. Imported unconditionally they kept this whole file
# from loading on Windows, the disk lane included, and the disk lane is the half a PC creator needs. So they load
# on the Mac only; on Windows the accessibility calls are stand-ins that say plainly what does work there.

if not ON_WINDOWS:
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,  # noqa: E402
                                     AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType)
    from Quartz import (CGEventCreateKeyboardEvent, CGEventCreateMouseEvent, CGEventPost,  # noqa: E402
                        CGEventSetFlags, CGEventSetIntegerValueField, kCGEventFlagMaskCommand,
                        kCGEventFlagMaskShift, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventMouseMoved,
                        kCGHIDEventTap, kCGMouseButtonLeft, kCGMouseEventClickState)
else:
    def _mac_only(*_args, **_kwargs):
        sys.exit("Driving the CapCut window directly is macOS only. Building and handing over a draft "
                 "works on this computer, so use that instead.")
    AXUIElementCreateApplication = AXUIElementCopyAttributeValue = AXValueGetValue = _mac_only
    kAXValueCGPointType = kAXValueCGSizeType = None
    # The synthesized mouse and keyboard are the Mac's too. Left undefined, `key`, `save`, `clickxy` and `export`
    # died on a NameError here instead of saying what does work on a PC.
    CGEventCreateKeyboardEvent = CGEventCreateMouseEvent = CGEventPost = _mac_only
    CGEventSetFlags = CGEventSetIntegerValueField = _mac_only
    kCGEventFlagMaskCommand = kCGEventFlagMaskShift = 0          # press() ORs these before its first event
    kCGEventLeftMouseDown = kCGEventLeftMouseUp = kCGEventMouseMoved = None
    kCGHIDEventTap = kCGMouseButtonLeft = kCGMouseEventClickState = None

# macOS virtual key codes, in code order, for the keys a live command ever needs.
KEYCODES = {"a": 0, "s": 1, "z": 6, "c": 8, "v": 9, "b": 11,
            "return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53,
            "left": 123, "right": 124, "down": 125, "up": 126}


def capcut_ax():
    pid = capcut_pid()
    if pid is not None:
        return AXUIElementCreateApplication(pid)
    sys.exit("CapCut is not open. Start it first with: launch")


def ax(element, attribute):
    """One accessibility attribute, or None when the element does not carry it."""
    status, value = AXUIElementCopyAttributeValue(element, attribute, None)
    return value if status == 0 else None


def frame(element):
    """Where an element sits on screen as (x, y, width, height), or None for one with no geometry."""
    has_origin, origin = AXValueGetValue(ax(element, "AXPosition"), kAXValueCGPointType, None)
    has_size, size = AXValueGetValue(ax(element, "AXSize"), kAXValueCGSizeType, None)
    if not (has_origin and has_size):
        return None
    return origin.x, origin.y, size.width, size.height


def centre(box):
    x, y, width, height = box
    return x + width / 2, y + height / 2


def descend(element, depth=0):
    """Pre-order walk, each element before its children, from depth 0 (the window) down to depth 18 and no
    further."""
    if depth <= 18:
        yield element
        for child in ax(element, "AXChildren") or []:
            yield from descend(child, depth + 1)


def on_screen(needle=None):
    """Every element in every CapCut window whose label contains `needle` (any case), as (element, label, frame).
    The label is the title when there is one and the description otherwise; CapCut puts its ids in either."""
    wanted = None if needle is None else needle.lower()
    matches = []
    for window in ax(capcut_ax(), "AXWindows") or []:
        for element in descend(window):
            label = ax(element, "AXTitle") or ax(element, "AXDescription") or ""
            if wanted is None or wanted in label.lower():
                matches.append((element, label, frame(element)))
    return matches


def find(needle, timeout=0):
    """The first element matching `needle` that has a place on screen, polling for up to `timeout` seconds."""
    began = time.time()
    while True:
        placed = [hit for hit in on_screen(needle) if hit[2]]
        if placed:
            return placed[0]
        if time.time() - began >= timeout:
            return None
        time.sleep(POLL_SECONDS)


def readout():
    """CapCut's own playhead and total-length readouts, as the timecode text after the '|' ('?' if absent)."""
    at, total = find("currentProgress"), find("totalProgress")

    def timecode(hit):
        return (ax(hit[0], "AXDescription") or "").split("|")[-1] if hit else "?"
    return timecode(at), timecode(total)


# ---------------------------------------------------------------------------------------------- acting on the screen

def click(x, y, times=1):
    """Move to (x, y), then press and release `times` times. Each press carries its click count, which is how a
    double-click reaches CapCut as one gesture rather than two single clicks."""
    point = (x, y)
    moved = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, moved)
    time.sleep(0.05)
    for count in range(1, times + 1):
        for phase in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
            event = CGEventCreateMouseEvent(None, phase, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event, kCGMouseEventClickState, count)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(0.05)


def click_on(needle, times=1, timeout=5):
    """Click the centre of the element labelled `needle`; returns the label it actually clicked."""
    hit = find(needle, timeout)
    if not hit:
        sys.exit(f"no element on screen matches: {needle}")
    click(*centre(hit[2]), times)
    return hit[1]


_forward = False


def bring_forward():
    """A synthesized keystroke goes to whichever app is frontmost, so CapCut is activated (once per run) before
    the first one. A click lands by position and needs none of this. Without it `key space` did nothing at all
    while `seek` worked fine, only because seek's ruler click happened to bring CapCut forward first."""
    global _forward
    if _forward:
        return
    tell_capcut("activate")
    time.sleep(0.4)
    _forward = True


def press(combo):
    """Press a key such as 'space', 'escape' or 'cmd+shift+z'. cmd and shift are the only modifiers read."""
    bring_forward()
    keys = combo.lower().split("+")
    main_key = keys[-1]
    if main_key not in KEYCODES:
        sys.exit(f"no key code for {main_key}. Keys it knows: {', '.join(sorted(KEYCODES))}")
    held = (kCGEventFlagMaskCommand if "cmd" in keys else 0) | (kCGEventFlagMaskShift if "shift" in keys else 0)
    for is_down in (True, False):
        event = CGEventCreateKeyboardEvent(None, KEYCODES[main_key], is_down)
        if held:
            CGEventSetFlags(event, held)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.03)


# ---------------------------------------------------------------------------------------------- the timeline, live

RULER_BELOW_TOOLBAR = 33   # px from the top of the timeline toolbar down to the ruler row


def timecode_seconds(stamp, fps):
    hours, minutes, seconds, frames = (int(part) for part in stamp.split(":"))
    return hours * 3600 + minutes * 60 + seconds + frames / fps


def saved_fps(name=None):
    """The frame rate a draft was saved with; 30.0 when there is no draft or it cannot be read."""
    if name:
        try:
            return json.load(open(_ds.draft_json(str(DRAFTS / name)), encoding="utf-8"))["fps"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return 30.0


def playhead_at(fps):
    stamp, _ = readout()
    return None if stamp == "?" else timecode_seconds(stamp, fps)


def clips_on_timeline():
    """Every clip on the timeline, main track and overlays together, as (label, x, y, width, height) sorted top
    to bottom and then left to right."""
    boxes = [(label, *box) for _, label, box in on_screen("MTLSVideoP") if box]
    return sorted(boxes, key=lambda clip: (clip[2], clip[1]))


def ruler_row():
    toolbar = find("cutoff") or find("undo")
    if not toolbar:
        sys.exit("can't see the timeline toolbar. Is a draft open?")
    return toolbar[2][1] + RULER_BELOW_TOOLBAR


def ruler_click(x, y=None):
    row = ruler_row() if y is None else y
    click(x, row)
    time.sleep(0.35)


def ruler_scale(fps):
    """Learn how the ruler maps pixels to seconds right now, by clicking it twice and reading CapCut's own playhead
    each time. Nothing is assumed about where the timeline starts, the zoom, or the scroll position."""
    clips = clips_on_timeline()
    if not clips:
        sys.exit("no clips on the timeline to calibrate against")
    left = min(clip[1] for clip in clips)
    span = max(clip[1] + clip[3] for clip in clips) - left
    x1, x2 = left + span * 0.2, left + span * 0.6
    ruler_click(x1)
    t1 = playhead_at(fps)
    ruler_click(x2)
    t2 = playhead_at(fps)
    if t1 is None or t2 is None or abs(t2 - t1) < 1e-6:
        sys.exit("calibration failed (playhead did not move)")
    seconds_per_px = (t2 - t1) / (x2 - x1)
    return (lambda t: x1 + (t - t1) / seconds_per_px), seconds_per_px


def seek(seconds, fps=30.0, within_frames=0):
    """Put the playhead on one exact frame. One click where the ruler says that time is, then arrow-key frame steps
    (twelve at most per round) for whatever error is left, re-reading CapCut's readout after every round."""
    to_x, _ = ruler_scale(fps)
    ruler_click(to_x(seconds))
    for _ in range(60):
        landed = playhead_at(fps)
        if landed is None:
            break
        off_by = round((seconds - landed) * fps)
        if abs(off_by) <= within_frames:
            return landed
        for _ in range(min(abs(off_by), 12)):
            press("right" if off_by > 0 else "left")
        time.sleep(0.15)
    return playhead_at(fps)


def pick_clip(index):
    row = clips_on_timeline()
    if index >= len(row):
        sys.exit(f"there is no clip {index} — the timeline holds {len(row)}")
    label, *box = row[index]
    click(*centre(box))
    time.sleep(0.5)
    return label


def capcut_window_number():
    """The window server's number for CapCut's biggest on-screen window (the first one if two tie)."""
    if ON_WINDOWS:
        _mac_only()
    from Quartz import CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListOptionOnScreenOnly
    biggest = None
    for window in CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID):
        if window.get("kCGWindowOwnerName") != APP_NAME:
            continue
        bounds = window["kCGWindowBounds"]
        area = bounds["Width"] * bounds["Height"]
        if biggest is None or area > biggest[1]:
            biggest = (window["kCGWindowNumber"], area)
    return biggest[0] if biggest else None


def screenshot(destination):
    """A picture of the CapCut window, for looking at whether a graphic landed where it should."""
    number = capcut_window_number()
    if number is None:
        sys.exit("CapCut has no window on screen to capture")
    picture = Path(destination).expanduser().resolve()
    subprocess.run(["screencapture", "-x", "-o", "-l", str(number), str(picture)], check=True)
    return picture


# ---------------------------------------------------------------------------------------------- CapCut's JSON shapes
# Each shape below is an object this writes into a draft, field for field, in a fixed order. Keep that order when
# editing a shape: the self-heal playbook starts by diffing a draft from here against one CapCut made itself, and
# a stable order keeps that diff readable. A bare type stands for that type's blank value (str "", int 0,
# float 0.0, bool False, list []), NULL is JSON null, and anything else is written exactly as it is.

NULL = None


def blank(shape):
    """A fresh object built from a shape, nested dicts and lists included. Nothing is shared between two calls,
    so no two segments can ever end up holding the same list."""
    if isinstance(shape, type):
        return shape()
    if isinstance(shape, dict):
        return {field: blank(value) for field, value in shape.items()}
    if isinstance(shape, list):
        return [blank(item) for item in shape]
    return shape


def new_id():
    return str(uuid.uuid4()).upper()


def _corners(**points):
    """A crop box the way CapCut stores it: each named corner's x, then its y, as fractions of the frame."""
    return {f"{corner}_{axis}": value for corner, (x, y) in points.items() for axis, value in (("x", x), ("y", y))}


# One source file in the draft's media pool, uncropped.
MEDIA_SHAPE = {
    "id": str, "unique_id": str, "type": "video", "duration": int, "path": str, "media_path": str,
    "local_id": str, "has_audio": bool, "reverse_path": str, "intensifies_path": str,
    "reverse_intensifies_path": str, "intensifies_audio_path": str, "cartoon_path": str, "width": int,
    "height": int, "category_id": str, "category_name": str, "material_id": str, "material_name": str,
    "material_url": str,
    "crop": _corners(upper_left=(0.0, 0.0), upper_right=(1.0, 0.0), lower_left=(0.0, 1.0), lower_right=(1.0, 1.0)),
    "crop_ratio": "free", "audio_fade": NULL, "crop_scale": 1.0, "extra_type_option": int,
    "stable": {"stable_level": int, "matrix_path": str, "time_range": {"start": int, "duration": int}},
    "matting": {"flag": int, "path": str, "interactiveTime": list, "has_use_quick_brush": bool, "strokes": list,
                "has_use_quick_eraser": bool, "expansion": int, "feather": int, "reverse": bool,
                "custom_matting_id": str, "enable_matting_stroke": bool, "is_clould": bool,
                "mask_video_path": str, "cloud_product_fps": float},
    "source": int, "source_platform": int, "formula_id": str, "check_flag": 62978047,
    "video_algorithm": {"algorithms": list, "time_range": NULL, "path": str, "gameplay_configs": list,
                        "ai_in_painting_config": list, "complement_frame_config": NULL,
                        "motion_blur_config": NULL, "deflicker": NULL, "noise_reduction": NULL,
                        "quality_enhance": NULL, "super_resolution": NULL, "ai_background_configs": list,
                        "smart_complement_frame": NULL, "aigc_generate": NULL, "aigc_generate_list": list,
                        "mouth_shape_driver": NULL, "ai_expression_driven": NULL, "ai_motion_driven": NULL,
                        "image_interpretation": NULL,
                        "story_video_modify_video_config": {"task_id": str, "is_overwrite_last_video": bool,
                                                            "tracker_task_id": str, "generate_id": str,
                                                            "generate_card_id": str},
                        "skip_algorithm_index": list},
    "is_unified_beauty_mode": bool, "is_set_beauty_mode": bool, "object_locked": NULL, "smart_motion": NULL,
    "multi_camera_info": NULL, "freeze": NULL, "picture_from": "none", "picture_set_category_id": str,
    "picture_set_category_name": str, "team_id": str, "local_material_id": str, "origin_material_id": str,
    "request_id": str, "has_sound_separated": bool, "is_text_edit_overdub": bool,
    "is_ai_generate_content": bool, "aigc_type": "none", "is_copyright": bool, "aigc_history_id": str,
    "aigc_item_id": str, "local_material_from": str, "smart_match_info": NULL, "beauty_face_preset_infos": list,
    "beauty_body_preset_id": str,
    "beauty_face_auto_preset": {"preset_id": str, "name": str, "rate_map": str, "scene": str},
    "beauty_face_auto_preset_infos": list, "beauty_body_auto_preset": NULL, "live_photo_timestamp": -1,
    "live_photo_cover_path": str, "content_feature_info": NULL, "corner_pin": NULL, "surface_trackings": list,
    "video_mask_stroke": {"resource_id": str, "path": str, "type": str, "color": str, "size": float,
                          "alpha": float, "distance": float, "texture": float, "horizontal_shift": float,
                          "vertical_shift": float},
    "video_mask_shadow": {"resource_id": str, "path": str, "color": str, "alpha": float, "blur": float,
                          "distance": float, "angle": float},
}

# One clip on a track: the part of a source it plays and where on the timeline it plays it.
SEGMENT_SHAPE = {
    "id": str,
    "source_timerange": {"start": int, "duration": int},
    "target_timerange": {"start": int, "duration": int},
    "render_timerange": {"start": int, "duration": int},
    "desc": str, "state": int, "speed": 1.0, "is_loop": bool, "is_tone_modify": bool, "reverse": bool,
    "intensifies_audio": bool, "cartoon": bool, "volume": 1.0, "last_nonzero_volume": 1.0,
    "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": float, "transform": {"x": float, "y": float},
             "flip": {"vertical": bool, "horizontal": bool}, "alpha": 1.0},
    "uniform_scale": {"on": True, "value": 1.0}, "material_id": str, "extra_material_refs": list,
    "render_index": int, "keyframe_refs": list,
    "enable_lut": True, "enable_adjust": True, "enable_hsl": bool, "visible": True, "group_id": str,
    "enable_color_curves": True, "enable_hsl_curves": True, "track_render_index": int,
    # Born SDR, never HDR: footage reaching CapCut is bt709 by now and mode 1 renders it washed out.
    # product/capcut_color.py owns that decision; product/tests/test_capcut_color.py reads this literal.
    "hdr_settings": {"mode": 0, "intensity": 1.0, "nits": 203},
    "enable_color_wheels": True, "track_attribute": int, "is_placeholder": bool, "template_id": str,
    "enable_smart_color_adjust": bool, "template_scene": "default", "common_keyframes": list,
    "caption_info": NULL,
    "responsive_layout": {"enable": bool, "target_follow": str, "size_layout": int,
                          "horizontal_pos_layout": int, "vertical_pos_layout": int},
    "enable_color_match_adjust": bool, "enable_color_correct_adjust": bool, "enable_adjust_mask": bool,
    "raw_segment_id": str, "lyric_keyframes": NULL, "enable_video_mask": True,
    "digital_human_template_group_id": str, "color_correct_alg_result": str, "source": "segmentsourcenormal",
    "enable_mask_stroke": bool, "enable_mask_shadow": bool, "enable_color_adjust_pro": bool,
}

# The six helper materials CapCut hangs off every clip it makes, keyed by the pool each one lives in.
SEGMENT_HELPERS = {
    "speeds": {"type": "speed", "mode": int, "speed": 1.0, "curve_speed": NULL},
    "placeholder_infos": {"type": "placeholder_info", "meta_type": "none", "res_path": str, "res_text": str,
                          "error_path": str, "error_text": str},
    "canvases": {"type": "canvas_color", "color": str, "blur": float, "image": str, "album_image": str,
                 "image_id": str, "image_name": str, "source_platform": int, "team_id": str},
    "sound_channel_mappings": {"type": str, "audio_channel_mapping": int, "is_config_open": bool},
    "material_colors": {"is_color_clip": bool, "is_gradient": bool, "solid_color": str, "gradient_colors": list,
                        "gradient_percents": list, "gradient_angle": 90.0, "width": float, "height": float},
    "vocal_separations": {"type": "vocal_separation", "choice": int, "removed_sounds": list, "time_range": NULL,
                          "production_path": str, "final_algorithm": str, "enter_from": str},
}

# One track. flag is its role to CapCut: 0 the main track, 1 text, 2 an overlay above the main track.
TRACK_SHAPE = {"id": str, "type": str, "segments": list, "flag": int, "attribute": int, "name": str,
               "is_default_name": True}

# A whole draft. The materials pools are listed in CapCut's order; the last seven are the ones replay fills.
DRAFT_SHAPE = {
    "id": str, "version": 360000, "new_version": "175.0.0", "name": str, "duration": int, "create_time": int,
    "update_time": int, "fps": 30.0, "is_drop_frame_timecode": bool, "color_space": int,
    "config": {"video_mute": bool, "record_audio_last_index": 1, "extract_audio_last_index": 1,
               "original_sound_last_index": 1, "subtitle_recognition_id": str, "subtitle_taskinfo": list,
               "lyrics_recognition_id": str, "lyrics_taskinfo": list, "subtitle_sync": True, "lyrics_sync": True,
               "voice_change_sync": bool, "sticker_max_index": 1, "adjust_max_index": 1,
               "material_save_mode": int, "export_range": NULL, "maintrack_adsorb": True,
               "combination_max_index": 1, "attachment_info": list, "zoom_info_params": NULL,
               "system_font_list": list, "multi_language_mode": "none", "multi_language_main": "none",
               "multi_language_current": "none", "multi_language_list": list, "subtitle_keywords_config": NULL,
               "use_float_render": bool},
    "canvas_config": {"ratio": "original", "width": int, "height": int, "background": NULL},
    "tracks": list, "group_container": NULL,
    "materials": {
        "flowers": list, "tail_leaders": list, "audios": list, "images": list, "texts": list, "effects": list,
        "stickers": list, "transitions": list, "audio_effects": list, "audio_fades": list, "beats": list,
        "material_animations": list, "placeholders": list, "common_mask": list, "chromas": list,
        "text_templates": list, "realtime_denoises": list, "audio_pannings": list, "audio_pitch_shifts": list,
        "video_trackings": list, "hsl": list, "drafts": list, "color_curves": list, "hsl_curves": list,
        "primary_color_wheels": list, "log_color_wheels": list, "video_effects": list, "ai_text_effects": list,
        "audio_balances": list, "handwrites": list, "manual_deformations": list, "manual_beautys": list,
        "plugin_effects": list, "green_screens": list, "shapes": list, "digital_humans": list,
        "digital_human_model_dressing": list, "smart_crops": list, "ai_translates": list,
        "audio_track_indexes": list, "loudnesses": list, "vocal_beautifys": list, "smart_relights": list,
        "time_marks": list, "multi_language_refs": list, "video_shadows": list, "video_strokes": list,
        "video_radius": list,
        "videos": list, "canvases": list, "speeds": list, "placeholder_infos": list,
        "sound_channel_mappings": list, "material_colors": list, "vocal_separations": list,
    },
    "keyframes": {"videos": list, "audios": list, "texts": list, "stickers": list, "filters": list,
                  "adjusts": list, "handwrites": list, "effects": list},
    "keyframe_graph_list": list, "platform": dict, "last_modified_platform": dict, "mutable_config": NULL,
    "cover": NULL, "retouch_cover": NULL, "extra_info": NULL, "relationships": list,
    "mixed_track_mode_on": bool, "render_index_track_mode_on": True, "free_render_index_mode_on": bool,
    "static_cover_image_path": str, "source": "default", "time_marks": NULL, "path": str,
    "lyrics_effects": list,
    "uneven_animation_template_info": {"composition": str, "content": str, "order": str,
                                       "sub_template_info_list": list},
    "draft_type": "video", "smart_ads_info": {"page_from": str, "routine": str, "draft_url": str},
}

# Stamped into a new draft when no draft on this machine has a platform block to borrow.
FALLBACK_PLATFORM = {"os": "mac", "os_version": str, "app_id": 359289, "app_version": "8.9.0",
                     "app_source": "cc", "device_id": str, "hard_disk_id": str, "mac_address": str}

# draft_meta_info.json, checked field by field against one CapCut wrote itself. It is a different schema from
# the registry row (capcut_media owns that one): this file carries draft_enterprise_info as a nested object next
# to the flat draft_cloud_* fields, plus the imported-media list. Do not flatten it.
META_SHAPE = {
    "cloud_draft_cover": bool, "cloud_draft_sync": bool, "cloud_package_completed_time": str,
    "draft_cloud_capcut_purchase_info": str, "draft_cloud_last_action_download": bool,
    "draft_cloud_package_type": str, "draft_cloud_purchase_info": str, "draft_cloud_template_id": str,
    "draft_cloud_tutorial_info": str, "draft_cloud_videocut_purchase_info": str,
    "draft_cover": "draft_cover.jpg", "draft_deeplink_url": str,
    "draft_enterprise_info": {"draft_enterprise_extra": str, "draft_enterprise_id": str,
                              "draft_enterprise_name": str, "enterprise_material": list},
    "draft_fold_path": str, "draft_has_unfinished_aigc_video_effect": bool, "draft_id": str,
    "draft_is_ae_produce": bool, "draft_is_ai_packaging_used": bool, "draft_is_ai_shorts": bool,
    "draft_is_ai_translate": bool, "draft_is_article_video_draft": bool, "draft_is_cloud_temp_draft": bool,
    "draft_is_from_deeplink": "false", "draft_is_infinite_canvas_draft": bool, "draft_is_invisible": bool,
    "draft_is_pippit_draft": bool, "draft_is_web_article_video": bool, "draft_materials": list,
    "draft_materials_copied_info": list, "draft_name": str, "draft_need_rename_folder": bool,
    "draft_new_version": str, "draft_removable_storage_device": str, "draft_root_path": str,
    "draft_segment_extra_info": list, "draft_timeline_materials_size_": int, "draft_type": str,
    "draft_web_article_video_enter_from": str, "pippit_avatar_url": str, "pippit_extra_info": str,
    "pippit_id": str, "pippit_user_name": str, "tm_draft_cloud_completed": str, "tm_draft_cloud_entry_id": -1,
    "tm_draft_cloud_modified": int, "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
    "tm_draft_cloud_user_id": -1, "tm_draft_create": int, "tm_draft_modified": int, "tm_draft_removed": int,
    "tm_duration": int,
}

# One row of the meta file's imported-media list (group type 0).
IMPORTED_SHAPE = {
    "ai_group_type": str, "create_time": int, "duration": int, "enter_from": int, "extra_info": str,
    "file_Path": str, "height": int, "id": str, "import_time": int, "import_time_ms": int, "item_source": 1,
    "md5": str, "metetype": "video", "roughcut_time_range": {"duration": int, "start": int},
    "sub_time_range": {"duration": -1, "start": -1}, "type": int, "width": int,
}


def new_track(kind, flag, segments=None):
    track = blank(TRACK_SHAPE)
    track.update(id=new_id(), type=kind, flag=flag)
    if segments is not None:
        track["segments"] = segments
    return track


def probe_video(path):
    """(width, height, duration in microseconds, has an audio stream) of a video file, via ffprobe."""
    listing = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                       "stream=codec_type,width,height,duration", "-of", "json", str(path)])
    streams = json.loads(listing)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    has_sound = any(stream["codec_type"] == "audio" for stream in streams)
    return int(video["width"]), int(video["height"]), int(float(video["duration"]) * 1e6), has_sound


def source_rotation(path):
    """How far a player turns this file's picture on playback, in degrees; 0 when the file says nothing. A phone
    filming upright stores the picture on its side (3840x2160) and records a -90 here, so the stored width and
    height alone call an upright reel landscape."""
    try:
        listing = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                           "stream_side_data=rotation:stream_tags=rotate", "-of", "json",
                                           str(path)])
        stream = (json.loads(listing).get("streams") or [{}])[0]
    except (subprocess.CalledProcessError, OSError, ValueError):
        return 0
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            return int(float(side["rotation"]))
    try:
        return int(float((stream.get("tags") or {}).get("rotate", 0)))
    except (TypeError, ValueError):
        return 0


def canvas_for(probed, rotation):
    """The draft's canvas, shaped like the footage as it plays: an upright 9:16 clip gets a 9:16 canvas and a
    landscape one gets 1920x1080, as before. The short side is 1080, the size every builder in the engine uses."""
    width, height = probed[0], probed[1]
    if rotation % 180:
        width, height = height, width
    if width <= 0 or height <= 0:
        return 1920, 1080
    scale = 1080 / min(width, height)
    return round(width * scale / 2) * 2, round(height * scale / 2) * 2


def media_entry(material_id, path, probed):
    width, height, length_us, has_sound = probed
    media = blank(MEDIA_SHAPE)
    media.update(id=material_id, path=str(path), material_name=Path(path).name, width=width, height=height,
                 duration=length_us, has_audio=has_sound)
    return media


def attach_helpers(pools):
    """Give one new clip its six helper materials; their ids, in order, become its extra_material_refs."""
    refs = []
    for pool, shape in SEGMENT_HELPERS.items():
        helper = {"id": new_id(), **blank(shape)}
        pools[pool].append(helper)
        refs.append(helper["id"])
    return refs


def clip_segment(pools, material_id, source_start, length, timeline_start):
    """A clip playing `length` microseconds of a source from `source_start`, placed at `timeline_start`."""
    refs = attach_helpers(pools)
    segment = blank(SEGMENT_SHAPE)
    segment["id"] = new_id()
    segment["source_timerange"] = {"start": source_start, "duration": length}
    segment["target_timerange"] = {"start": timeline_start, "duration": length}
    segment["material_id"] = material_id
    segment["extra_material_refs"] = refs
    return segment


def borrowed_platform():
    """The device block out of a draft CapCut made on this machine, so a draft written here reads as native.
    draft_jsons_under hands back path STRINGS; wrapping each in Path() matters, because calling .read_text() on a
    str raised an AttributeError the except below never caught and crashed replay the moment any draft existed."""
    for found in sorted(_ds.draft_jsons_under(str(DRAFTS))):
        try:
            return json.loads(Path(found).read_text(encoding="utf-8"))["platform"]
        except (KeyError, OSError, json.JSONDecodeError):
            continue
    return blank(FALLBACK_PLATFORM)


def write_compact(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def copy_in(source, into):
    """Hardlink `source` into a draft folder (no bytes move on one APFS volume), copying if linking fails."""
    try:
        into.hardlink_to(source)
    except OSError:
        shutil.copy2(source, into)


# ---------------------------------------------------------------------------------------------- replay

def draft_from_cuts(footage, cut_list, clip_of):
    """A complete draft playing the cut list: clips butt-joined in order on the main track, each one playing the
    source file its own cut names. `footage` maps each clip name to its copy inside the draft, in the order the
    cut list first uses them; `clip_of(cut)` names a cut's clip. Every cut used to play the FIRST clip, so a reel
    filmed in two takes came back as the first take cut to the second take's timings."""
    probes = {clip: probe_video(path) for clip, path in footage.items()}
    first = next(iter(footage))
    canvas = canvas_for(probes[first], source_rotation(footage[first]))
    platform = borrowed_platform()
    draft = blank(DRAFT_SHAPE)
    pools = draft["materials"]
    material_of = {}
    for clip, path in footage.items():
        material_of[clip] = new_id()
        pools["videos"].append(media_entry(material_of[clip], path, probes[clip]))
    main, timeline_at = [], 0
    for cut in cut_list["segments"]:
        source_at = round(cut["start"] * 1e6)
        length = round((cut["end"] - cut["start"]) * 1e6)
        main.append(clip_segment(pools, material_of[clip_of(cut)], source_at, length, timeline_at))
        timeline_at += length
    draft["id"] = new_id()
    draft["duration"] = timeline_at
    draft["canvas_config"]["width"], draft["canvas_config"]["height"] = canvas
    draft["tracks"] = [new_track("video", 0, main)]
    draft["platform"] = draft["last_modified_platform"] = platform
    return draft, probes


def meta_for(name, folder, draft_id, footage, probes, total_us, stamp_us):
    """draft_meta_info.json for a new draft: one imported-media row per source file it plays."""
    stamp_s = stamp_us // 1_000_000
    rows = []
    for clip, path in footage.items():
        width, height, raw_us, _ = probes[clip]
        imported = blank(IMPORTED_SHAPE)
        imported.update(id=str(uuid.uuid4()), file_Path=str(path), extra_info=Path(path).name, width=width,
                        height=height, duration=raw_us, create_time=stamp_s, import_time=stamp_s,
                        import_time_ms=stamp_us)
        imported["roughcut_time_range"]["duration"] = raw_us
        rows.append(imported)
    meta = blank(META_SHAPE)
    meta.update(draft_id=draft_id, draft_name=name, draft_fold_path=str(folder), draft_root_path=str(DRAFTS),
                tm_duration=total_us, tm_draft_create=stamp_us, tm_draft_modified=stamp_us)
    meta["draft_materials"] = ([{"type": 0, "value": rows}]
                               + [{"type": group, "value": []} for group in (1, 2, 3, 6, 7)])
    return meta


def replay(job, name=None):
    """Lay a job's rough cut down as a brand-new draft. Fresh drafts only: a draft she has already worked on in
    CapCut is built on with the add-* commands, never regenerated over."""
    job_dir = REPO / "projects" / job
    edl = job_dir / "transcript" / "cuts.json"
    if not edl.exists():
        sys.exit(f"no cut list (EDL) at {edl}. Run rough-cut with RENDER=0 first.")
    cut_list = json.loads(edl.read_text(encoding="utf-8"))
    first = cut_list["segments"][0]
    source_clip = job_dir / "raw" / first["clip"]

    def clip_of(cut):                                    # a cut that names no clip plays the first cut's
        return cut.get("clip") or first["clip"]
    clips = list(dict.fromkeys(clip_of(cut) for cut in cut_list["segments"]))
    for clip in clips:
        if not (job_dir / "raw" / clip).exists():
            sys.exit(f"the raw clip the cut list names is not there: {job_dir / 'raw' / clip}")
    name = name or job
    draft_dir = DRAFTS / name
    if draft_dir.exists():
        sys.exit(f"{draft_dir} already exists. Give the new draft a different --name.")

    was_open = capcut_pid() is not None
    if was_open and not ON_WINDOWS:                      # Windows refuses rather than kill it (close_for_write)
        print("closing CapCut first (it rewrites its list of drafts as it quits)...")
        quit_capcut()
    _ds.require_capcut_quit("add a new draft to CapCut's list")

    # CapCut's sandbox grants it assets.movies.read-write and nothing more, so it cannot read a file in the repo:
    # the footage has to sit inside the draft folder, under ~/Movies. One copy per source file the cut list plays.
    (draft_dir / "Resources").mkdir(parents=True)
    footage, taken = {}, set()
    for number, clip in enumerate(clips):
        local_name = Path(clip).name
        if local_name in taken:                          # two clips from different folders sharing a file name
            local_name = f"{number}-{local_name}"
        taken.add(local_name)
        footage[clip] = draft_dir / "Resources" / local_name
        copy_in(job_dir / "raw" / clip, footage[clip])

    draft, probes = draft_from_cuts(footage, cut_list, clip_of)
    enforce_maintrack_ripple(draft)
    stamp_us = time.time_ns() // 1000
    draft_id = new_id()
    write_compact(_ds.draft_json(str(draft_dir)), draft)
    write_compact(draft_dir / "draft_meta_info.json",
                  meta_for(name, draft_dir, draft_id, footage, probes, draft["duration"], stamp_us))
    # the home-screen tile's picture: the first kept frame. Cosmetic, so a failure here is ignored.
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(first["start"]), "-i", str(source_clip), "-frames:v", "1",
                    "-vf", "scale=480:-2", str(draft_dir / "draft_cover.jpg")], check=False)
    # The registry row comes from the same writer the builders' finalize() uses. A second hand-rolled copy of that
    # schema once lived here and drifted from what CapCut really writes.
    capcut_media.register_draft(str(DRAFTS), name, str(draft_dir), _ds.draft_json(str(draft_dir)), draft_id,
                                draft["duration"], stamp_us // 1_000_000)

    print(f"'{name}' holds {len(cut_list['segments'])} segments over {draft['duration'] / 1e6:.2f}s, in {draft_dir}")
    if was_open:
        start_capcut()
        print("CapCut is open again")


# ---------------------------------------------------------------------------------------------- changing a draft on disk

def existing_draft(name):
    draft_dir = DRAFTS / name
    if not draft_dir.exists():
        sys.exit(f"there is no draft named {name}")
    return draft_dir


@contextmanager
def editing(name):
    """Open an existing draft for a change on disk: `with editing(name) as (draft, folder): ...`.

    The draft is read as it stands, so whatever she changed by hand (CapCut saved it as it quit) is kept and built
    on. When the block finishes, the draft is written back and CapCut's caches for it are cleared, because CapCut
    only re-reads the JSON once they are gone; leave them and it quietly keeps what it already had, so the change
    never shows. If the block stops early (a refusal), nothing is written, and a CapCut this closed is opened again
    rather than left shut on her. CapCut is closed the way close_for_write says: asked to quit on a Mac, never
    killed on Windows (there a write while it is open is refused)."""
    folder = existing_draft(name)
    was_open = capcut_pid() is not None
    closed_it = was_open and not ON_WINDOWS             # a Mac closes it for the write; Windows refuses instead
    try:
        close_for_write("change this draft")

        timeline = _ds.draft_json(str(folder))
        draft = json.loads(Path(timeline).read_text(encoding="utf-8"))
        yield draft, folder

        # CapCut saves every text segment with a null source range. Harmless while CapCut holds the timeline, but
        # the cache clear below forces a re-import, and a null source range there wedged the export encoder
        # mid-render.
        for track in draft["tracks"]:
            for seg in track["segments"]:
                if seg.get("source_timerange") is None:
                    seg["source_timerange"] = {"start": 0, "duration": seg["target_timerange"]["duration"]}
        ends = [seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
                for track in draft["tracks"] for seg in track["segments"]]
        draft["duration"] = max(ends, default=0)
        write_compact(timeline, draft)
        Path(timeline + ".bak").unlink(missing_ok=True)
        # The timeline ids exist only as Timelines/ folder names, and the per-draft prerender cache is keyed by
        # them, so they are read before Timelines/ goes. Clearing Timelines/ alone left that cache behind, and a
        # replaced graphic kept showing its old picture after reopening.
        timeline_ids = _ds.draft_timeline_ids(str(folder))
        shutil.rmtree(folder / "Timelines", ignore_errors=True)
        cleared = _ds.clear_draft_caches(str(folder), timeline_ids)
        if cleared:
            print(f"  cleared {len(cleared)} stale prerender cache folder(s) for this draft")
    except BaseException:
        if closed_it:
            start_capcut()                               # stopped part-way: give her back the CapCut she had open
        raise

    if closed_it:
        start_capcut()
        time.sleep(8)
        open_draft(name)


def already_placed(draft, at_us, text=None, file_name=None):
    """Is this exact edit already in the draft? A run that died on the relaunch may well have written its change
    already, and repeating it would double it."""
    for track in draft["tracks"]:
        for seg in track["segments"]:
            if seg["target_timerange"]["start"] != at_us:
                continue
            if text is not None:
                material = _pooled(draft, "texts", seg["material_id"])
                if material and json.loads(material["content"]).get("text") == text:
                    return True
            if file_name is not None:
                material = _pooled(draft, "videos", seg["material_id"])
                if material and material["material_name"] == file_name:
                    return True
    return False


def _pooled(draft, pool, material_id):
    return next((entry for entry in draft["materials"][pool] if entry["id"] == material_id), None)


def media_into(folder, source):
    """Bring a media file inside the draft folder: sandboxed CapCut can read ~/Movies and nothing else."""
    source = Path(source).expanduser().resolve()
    if not source.exists():
        sys.exit(f"can't find the media file: {source}")
    local = folder / "Resources" / source.name
    if not local.exists():
        local.parent.mkdir(exist_ok=True)
        copy_in(source, local)
    return local


def _overlay_stack(draft):
    return [track for track in draft["tracks"] if track["type"] == "video" and track["flag"] == 2]


def overlay_track(draft, layer):
    """The overlay track for `layer`, counting up from 1 = just above the main track; a new one when the draft
    has fewer overlay tracks than that."""
    stacked = _overlay_stack(draft)
    if len(stacked) >= layer:
        return stacked[layer - 1]
    track = new_track("video", 2)
    draft["tracks"].append(track)
    return track


def free_layer(draft, at_us, length_us):
    """The lowest overlay layer with nothing on it between at_us and at_us + length_us. One CapCut track cannot
    hold two clips at the same moment, so a graphic that would land on top of another goes a layer up instead of
    being stacked onto the same track."""
    stacked = _overlay_stack(draft)
    for layer, track in enumerate(stacked, 1):
        taken = any(seg["target_timerange"]["start"] < at_us + length_us
                    and at_us < seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
                    for seg in track["segments"])
        if not taken:
            return layer
    return len(stacked) + 1


def lay_graphic(draft, folder, media, at_us, layer, length_us=None):
    """Put one graphic file on the overlay track for `layer`, starting at `at_us`; its full length when
    `length_us` is None. `layer=None` takes the lowest layer that is free for the graphic's whole span."""
    local = media_into(folder, media)
    probed = probe_video(local)
    material_id = new_id()
    draft["materials"]["videos"].append(media_entry(material_id, local, probed))
    length = probed[2] if length_us is None else length_us
    segment = clip_segment(draft["materials"], material_id, 0, length, at_us)
    if layer is None:
        layer = free_layer(draft, at_us, length)
    segment["render_index"] = layer
    segment["track_render_index"] = layer
    overlay_track(draft, layer)["segments"].append(segment)


def add_overlay(draft_name, media, at, layer=1, duration=None, force=False):
    """An alpha graphic (a ProRes 4444 .mov) laid over the cut, which is how step-3 graphics reach the timeline."""
    shown_as = Path(media).name
    with editing(draft_name) as (draft, folder):
        if not force and already_placed(draft, round(at * 1e6), file_name=shown_as):
            sys.exit(f"{shown_as} is already on the timeline at {at}s. Add --force to place a second copy.")
        lay_graphic(draft, folder, media, round(at * 1e6), layer, round(duration * 1e6) if duration else None)
    return f"overlay: {shown_as} at {at:.2f}s on layer {layer}"


def add_text(draft_name, text, at, duration=3.0, force=False):
    """A text clip built from templates lifted out of a real CapCut draft. The material's `content` is JSON inside
    JSON and carries the style runs, so each run's range is re-aimed at the new string; leave one pointing at the
    template's old length and the text comes back with no styling at all."""
    material_file = TEXT_TEMPLATES / "text-look.json"
    if not material_file.exists():
        sys.exit(f"the text template is missing: {material_file}")
    with editing(draft_name) as (draft, folder):
        if not force and already_placed(draft, round(at * 1e6), text=text):
            sys.exit(f"{text!r} is already on the timeline at {at}s. Add --force to place a second copy.")
        material = json.loads(material_file.read_text(encoding="utf-8"))
        content = json.loads(material["content"])
        content["text"] = text
        for run in content.get("styles", []):
            run["range"] = [0, len(text)]
        material["id"] = new_id()
        material["content"] = json.dumps(content, ensure_ascii=False)
        draft["materials"]["texts"].append(material)

        motion = json.loads((TEXT_TEMPLATES / "text-motion.json").read_text(encoding="utf-8"))
        motion["id"] = new_id()
        draft["materials"]["material_animations"].append(motion)

        segment = json.loads((TEXT_TEMPLATES / "text-clip.json").read_text(encoding="utf-8"))
        segment["id"] = new_id()
        segment["material_id"] = material["id"]
        segment["extra_material_refs"] = [motion["id"]]
        length = round(duration * 1e6)
        segment["source_timerange"] = {"start": 0, "duration": length}
        segment["target_timerange"] = {"start": round(at * 1e6), "duration": length}
        text_track = next((track for track in draft["tracks"] if track["type"] == "text"), None)
        if text_track is None:
            text_track = new_track("text", 1)
            draft["tracks"].append(text_track)
        text_track["segments"].append(segment)
    return f"text {text!r} on screen from {at:.2f}s, {duration:.2f}s long"


ROLES = ("main", "text", "overlay")


def main_track(draft):
    """The footage track: the one the magnet anchors every other track to. CapCut marks an overlay flag 2, but a
    draft the builders made through VectCut carries flag 0 on EVERY track, so the flag alone cannot tell main from
    overlay there. What can is the anchor (is_default_name False) and then the clip count, which is how
    capcut_ripple picks the main track when it anchors one."""
    videos = [track for track in draft["tracks"] if track["type"] == "video"]
    candidates = [track for track in videos if track.get("flag") != 2] or videos
    return max(candidates, key=lambda track: (track.get("is_default_name") is False, len(track["segments"])),
               default=None)


def role_tracks(draft, role):
    """The tracks playing one role, in draft order, chosen by what they hold rather than by flag. Choosing by flag
    found no text or overlay at all in a VectCut-built draft (flag 0 everywhere), and `main` reached into its text
    and sound tracks, so `remove --track main` could delete a caption or a sound."""
    main = main_track(draft)
    if role == "main":
        return [main] if main is not None else []
    if role == "overlay":
        return [track for track in draft["tracks"] if track["type"] == "video" and track is not main]
    return [track for track in draft["tracks"] if track["type"] == "text"]


def role_of(draft, track):
    """How `state` labels a track, in the words --track takes; a sound track is labelled by its type."""
    if track["type"] == "video":
        return "main" if track is main_track(draft) else "overlay"
    return track["type"]


def remove_segment(draft_name, role, index):
    """Take one clip out, plus any video or text material nothing plays any more. The disk-lane twin of the live
    `delete`: the one to use when the removal must be exact, or when there are many."""
    if role not in ROLES:
        raise KeyError(role)
    with editing(draft_name) as (draft, _):
        # CapCut spreads overlapping clips of one role across several tracks, so the index counts across all of
        # them: "text[1]" is the second text clip, wherever it sits, not something on track 1.
        slots = [(track, i) for track in role_tracks(draft, role) for i in range(len(track["segments"]))]
        if index >= len(slots):
            sys.exit(f"there is no {role} segment {index}: the draft holds {len(slots)}")
        track, position = slots[index]
        del track["segments"][position]
        playing = {seg["material_id"] for other in draft["tracks"] for seg in other["segments"]}
        for pool in ("videos", "texts"):
            draft["materials"][pool] = [entry for entry in draft["materials"][pool] if entry["id"] in playing]
        if role != "main" and not track["segments"]:
            draft["tracks"].remove(track)
    return f"removed {role}[{index}]"


def set_transform(draft_name, role, index, scale=None, x=None, y=None, rotation=None, opacity=None):
    """Scale, position, rotation and opacity of one clip, written into the draft exactly. Disk lane on purpose:
    the inspector's number fields take focus and then ignore a synthesized keystroke, which leaves the JSON as
    both the precise route and the only one that holds. x and y are fractions of the canvas, so y=-0.25 lifts
    the clip a quarter of a frame; scale is a plain multiplier."""
    if role not in ROLES:
        raise KeyError(role)
    with editing(draft_name) as (draft, _):
        tracks = role_tracks(draft, role)
        if not tracks:
            sys.exit(f"no {role} track in this draft")
        segments = tracks[0]["segments"]
        if index >= len(segments):
            sys.exit(f"{role} track has {len(segments)} segments, no index {index}")
        segment = segments[index]
        clip = segment["clip"]
        if scale is not None:
            clip["scale"] = {"x": scale, "y": scale}
            segment["uniform_scale"] = {"on": True, "value": scale}
        if x is not None:
            clip["transform"]["x"] = x
        if y is not None:
            clip["transform"]["y"] = y
        if rotation is not None:
            clip["rotation"] = rotation
        if opacity is not None:
            clip["alpha"] = opacity
    asked = {"scale": scale, "x": x, "y": y, "rotation": rotation, "opacity": opacity}
    applied = {field: value for field, value in asked.items() if value is not None}
    return f"{role}[{index}] transform: {applied}"


def place_plan(draft_name, job):
    """Every rendered graphic a job's graphics plan names, placed in one disk pass so CapCut's caches are rebuilt
    once rather than once per graphic."""
    job_dir = REPO / "projects" / job
    plan_file = job_dir / "graphics-plan.json"
    if not plan_file.exists():
        sys.exit(f"this job has no graphics plan yet: {plan_file}")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    ready = []
    for beat in plan.get("graphics") or plan.get("beats") or []:
        file_name = beat.get("file") or (f"{beat['id']}.mov" if beat.get("id") else None)
        # The first of the three names a plan may use for the time that is actually set. An `or` chain read a
        # graphic planned at 0 seconds as "no time given" and skipped it.
        start = next((beat[key] for key in ("start", "t", "time") if beat.get(key) is not None), None)
        if not file_name or start is None:
            continue
        rendered = job_dir / "assets" / file_name
        if not rendered.exists():
            print(f"  skipping {file_name}, which has not been rendered yet")
            continue
        ready.append((rendered, float(start)))
    if not ready:
        sys.exit("nothing in this plan can be placed yet")
    with editing(draft_name) as (draft, folder):
        for rendered, start in ready:
            lay_graphic(draft, folder, rendered, round(start * 1e6), None)   # layer 1 unless it would overlap
    return f"placed {len(ready)} graphic(s) from {job}'s plan"


# ---------------------------------------------------------------------------------------------- the magnet

def magnet(name):
    """THE magnet fix and its fail-safe. On a draft's first import CapCut rebuilds its Timelines/ cache and resets
    the main-track anchor there, which silently kills the magnet; the anchor written into the draft at build time
    is ignored from then on. This writes it back into every copy AFTER that import. Run it once, after the fresh
    draft has been opened. capcut_ripple.py explains it in full ("THE TIMELINES RESET")."""
    folder = existing_draft(name)
    if not _ds.draft_jsons_under(str(folder), "Timelines/*"):
        sys.exit(f"'{name}' has no Timelines cache yet — open it in CapCut once (so CapCut builds the "
                 f"cache), then run: magnet \"{name}\"")
    close_for_write("fix the magnet in this draft")      # CapCut rewrites the draft when it saves
    patched, problems = snap_draft_dir(str(folder))
    if problems:
        print("✗ MAGNET STILL BROKEN after snap:")
        _list_problems(problems)
        sys.exit(1)
    print(f"✓ magnet snapped into {patched} draft copies (top-level + Timelines) — every copy anchored.")
    start_capcut()
    if not ON_WINDOWS:
        # Launching lands on CapCut's home screen, so the draft is opened again too; without it the very next
        # `export` could not find the export button ("is a draft open?"). The magnet is already fixed by now, so
        # a draft that will not open is said plainly and does not fail the command.
        time.sleep(8)
        try:
            open_draft(name)
        except SystemExit as why:
            print(f"  could not open '{name}' by itself ({why}). Open it from CapCut's home screen before "
                  f"the next live command.")
    print(f"reopened '{name}' — trim/delete any main cut and the timeline ripples.")


def verify_magnet(name):
    """FAIL-SAFE: check the anchor in EVERY copy of the timeline JSON, top level and Timelines/ alike, and exit
    non-zero if any is broken. A reset Timelines/ copy cannot be seen from the top-level file."""
    folder = existing_draft(name)
    try:
        problems = verify_draft_dir(str(folder))
    except RuntimeError as refusal:
        # verify_draft_dir refuses to call zero files clean; that means this folder has no timeline JSON at all.
        sys.exit(f"cannot verify '{name}': {refusal}")
    if problems:
        print(f"✗ magnet BROKEN in '{name}':")
        _list_problems(problems)
        sys.exit(1)
    print(f"✓ magnet OK in '{name}' — all draft copies anchored.")


def _list_problems(problems):
    for copy, what in problems.items():
        print("  ", copy, "->", what)


# ---------------------------------------------------------------------------------------------- live commands

def find_title(name, timeout=0):
    """The home-screen title of exactly this draft, polling for up to `timeout` seconds. `find` takes any label
    that merely CONTAINS the text, which let `open "Reel 1.1"` double-click "Reel 1.12". A title has to be the
    whole name here; letter case and stray spaces around it are forgiven, nothing else is."""
    wanted = f"HomePageDraftTitle:{name}"
    began = time.time()
    while True:
        titles = [hit for hit in on_screen(wanted) if hit[2]]          # every title that CONTAINS the name
        exact = ([hit for hit in titles if hit[1] == wanted]
                 or [hit for hit in titles if hit[1].strip().lower() == wanted.strip().lower()])
        if exact:
            return exact[0]
        if time.time() - began >= timeout:
            return None
        time.sleep(POLL_SECONDS)


def open_draft(name):
    """Open a draft from CapCut's home screen by double-clicking its tile."""
    if capcut_pid() is None:
        start_capcut()
    tell_capcut("activate")
    hit = find_title(name, timeout=15)
    if not hit:
        press("escape")                                  # a promo panel can cover the home screen right after launch
        hit = find_title(name, timeout=15)
    if not hit:
        sys.exit(f"can't see a draft called {name} on CapCut's home screen")
    time.sleep(1.5)                                      # the window shifts once after launch, so look it up again
    hit = find_title(name, timeout=10) or hit
    tx, ty = hit[2][:2]
    # What takes the double-click is the HomePageDraft element whose left-to-right span holds the title.
    tile = next((box for _, label, box in on_screen("HomePageDraft")
                 if label == "HomePageDraft" and box and box[0] <= tx <= box[0] + box[2] and box[1] <= ty), None)
    click(*(centre(tile) if tile else (tx, ty - 60)), times=2)
    if find("MainTimeLineRoot", timeout=25) is None:
        sys.exit("double-clicked the draft, but the editor never opened")
    _, total = readout()
    print(f"opened '{name}', duration {total}")


# The export dialog is a fixed-size QML overlay centred on the CapCut window and, like Link media, it shows
# nothing to accessibility, so its controls are reached by offset from the window's centre (measured on 8.9.0).
EXPORT_BUTTON_FROM_CENTRE = (308, 302)
SYNC_TOGGLE_FROM_CENTRE = (6, 239)


def export(to=None, timeout=900, toggle_sync=False):
    """Run CapCut's export dialog start to finish, then wait for the file and report it.

    The dialog's defaults (the draft's name, into ~/Downloads) already match how this engine names exports. Its
    cloud checkbox, "Sync exported videos to space", is off, the dialog remembers whatever it was last left on,
    and a blind click would turn it back on, so nothing here touches it unless --toggle-sync asks for exactly
    that."""
    folder = Path(to).expanduser() if to else Path.home() / "Downloads"
    seen = {mp4: mp4.stat().st_mtime for mp4 in folder.glob("*.mp4")}

    # A finished export leaves a modal share screen up front, and it swallows the next export: the title-bar
    # click goes nowhere and the wait below runs its full length on a file nothing is writing. Escape it first.
    press("escape")
    time.sleep(1.0)
    if find("MainWindowTitleBarExportBtn") is None:
        sys.exit("can't find CapCut's Export button. Is a draft open?")
    window = next((box for _, _, box in on_screen("CapCut") if box and box[2] > 1000), None)
    if window is None:
        sys.exit("can't tell where the CapCut window is on screen")
    cx, cy = centre(window)

    click_on("MainWindowTitleBarExportBtn")
    time.sleep(6)                                        # the dialog is still drawing well after the click returns
    if toggle_sync:
        click(cx + SYNC_TOGGLE_FROM_CENTRE[0], cy + SYNC_TOGGLE_FROM_CENTRE[1])
        time.sleep(0.6)
    click(cx + EXPORT_BUTTON_FROM_CENTRE[0], cy + EXPORT_BUTTON_FROM_CENTRE[1])

    # Done means: the newest new-or-changed mp4 has held one non-zero size for two checks running.
    started, size, steady, newest, finished = time.time(), -1, 0, None, False
    while time.time() - started < timeout:
        time.sleep(4)
        moved = [mp4 for mp4 in folder.glob("*.mp4") if mp4 not in seen or mp4.stat().st_mtime > seen[mp4]]
        if not moved:
            continue
        newest = max(moved, key=lambda mp4: mp4.stat().st_mtime)
        now = newest.stat().st_size
        steady = steady + 1 if now == size and now > 0 else 0
        size = now
        if steady >= 2:
            finished = True
            break
    # Clear the share screen so the next command finds a normal window. Never click through it: it publishes
    # to TikTok and YouTube.
    press("escape")
    time.sleep(0.8)
    if newest is None:
        sys.exit("no file came out of that export. The dialog may still be sitting open")
    if not finished:
        # The wait ran out while the file was still growing. Calling that "landed" handed over half a video.
        sys.exit(f"the export had not finished when the {timeout}s wait ran out: {newest} was still being "
                 f"written ({max(size, 0) / 1048576:.1f} MB so far). Let CapCut finish, then check that file, "
                 f"or run export again with a longer --timeout.")

    length = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                             str(newest)], capture_output=True, text=True).stdout.strip() or "?"
    print(f"export landed: {newest}  {size / 1048576:.1f} MB  {length}s")
    return newest


def timeline_state(name=None):
    """The timeline as JSON. Clip times come from the saved draft, which is what CapCut will actually use, and
    the live clip count from the app is checked against it: edits made in the app reach disk only on save or
    quit, so a mismatch means there is unsaved work open."""
    at, total = readout()
    live = clips_on_timeline()
    report = {"playhead": at, "duration": total, "live_clip_count": len(live)}
    saved = Path(_ds.draft_json(str(DRAFTS / name))) if name else None
    if saved and saved.exists():
        draft = json.loads(saved.read_text(encoding="utf-8"))
        tracks = []
        for track in draft["tracks"]:
            rows = [_segment_row(draft, i, seg) for i, seg in enumerate(track["segments"])]
            tracks.append({"type": track["type"], "role": role_of(draft, track), "segments": rows})
        report["saved"] = {"duration": round(draft["duration"] / 1e6, 3), "tracks": tracks}
        on_disk = sum(len(track["segments"]) for track in draft["tracks"] if track["type"] == "video")
        if on_disk != len(live):
            report["unsaved_edits"] = f"{len(live)} clips open in the app against {on_disk} on disk"
    print(json.dumps(report, indent=1))


def _segment_row(draft, i, seg):
    """One clip for `state`: what it plays (file name, or the first 40 characters of its text) and its times."""
    shows = next((entry["material_name"] for entry in draft["materials"]["videos"]
                  if entry["id"] == seg["material_id"]), None)
    if shows is None:
        shows = next((json.loads(entry["content"]).get("text", "")[:40] for entry in draft["materials"]["texts"]
                      if entry["id"] == seg["material_id"]), "?")
    played = seg["target_timerange"]
    source = seg.get("source_timerange")                # null on text clips once CapCut has saved them
    return {"i": i, "media": shows, "start": round(played["start"] / 1e6, 3),
            "dur": round(played["duration"] / 1e6, 3), "src": round(source["start"] / 1e6, 3) if source else None}


def list_clips():
    placed = [(label, box) for _, label, box in on_screen("MTLSVideoP") if box]
    for label, (x, y, width, height) in sorted(placed, key=lambda item: item[1][0]):
        print(f"{label}  x={x:.0f} y={y:.0f} w={width:.0f} h={height:.0f}")
    print(f"{len(placed)} clip(s) on timeline")


# ---------------------------------------------------------------------------------------------- command line
# Each command is a small handler that takes the words after the command name. Whatever a handler returns is the
# line the command ends on; the ones that print as they go (replay, open, export, state...) return nothing.

def flag(args, name, cast=str, default=None):
    """The value after `name` in args, cast; `default` (as given, never cast) when the flag is absent."""
    if name not in args:
        return default
    return cast(args[args.index(name) + 1])


COMMANDS = {}


def command(*names):
    def register(handler):
        for each in names:
            COMMANDS[each] = handler
        return handler
    return register


# ---- on disk: CapCut is closed around each write

@command("replay")
def _replay(args):
    replay(args[0], flag(args, "--name"))


@command("add-overlay")
def _add_overlay(args):
    return add_overlay(args[0], args[1], flag(args, "--at", float, 0.0), flag(args, "--layer", int, 1),
                       flag(args, "--dur", float), force="--force" in args)


@command("add-text")
def _add_text(args):
    return add_text(args[0], args[1], flag(args, "--at", float, 0.0), flag(args, "--dur", float, 3.0),
                    force="--force" in args)


@command("remove")
def _remove(args):
    return remove_segment(args[0], flag(args, "--track", str, "main"), flag(args, "--index", int, 0))


@command("graphics")
def _graphics(args):
    return place_plan(args[0], args[1])


@command("transform")
def _transform(args):
    return set_transform(args[0], flag(args, "--track", str, "main"), flag(args, "--index", int, 0),
                         scale=flag(args, "--scale", float), x=flag(args, "--x", float), y=flag(args, "--y", float),
                         rotation=flag(args, "--rotate", float), opacity=flag(args, "--opacity", float))


@command("ls")
def _ls(args):
    registry = json.loads((DRAFTS / "root_meta_info.json").read_text(encoding="utf-8"))
    for row in registry["all_draft_store"]:
        print(f"{row['draft_name']} — {row['tm_duration'] / 1e6:.2f}s — {row['draft_fold_path']}")


@command("magnet")
def _magnet(args):
    magnet(args[0])


@command("verify-magnet")
def _verify_magnet(args):
    verify_magnet(args[0])


# ---- the open editor: nothing restarts

@command("open")
def _open(args):
    open_draft(args[0])


@command("launch")
def _launch(args):
    start_capcut()


@command("quit")
def _quit(args):
    quit_capcut()


@command("seek")
def _seek(args):
    wanted = float(args[0])
    landed = seek(wanted, saved_fps(flag(args, "--draft")))
    return f"playhead: {landed:.3f}s (target {wanted:.3f}s)"


@command("select")
def _select(args):
    return f"selected: {pick_clip(int(args[0]))}"


@command("split")
def _split(args):
    if args and not args[0].startswith("--"):          # a leading time means "go there first"; -- starts a flag
        seek(float(args[0]), saved_fps(flag(args, "--draft")))
    click_on("cutoff")
    return "split at playhead"


@command("delete", "del")
def _delete(args):
    pick_clip(int(args[0]))
    click_on("del")
    return f"deleted clip {args[0]}"


def _button(element, said):
    def handler(args):
        click_on(element)
        return said
    return handler


COMMANDS.update({"trim-left": _button("cutLeft", "trim-left at playhead"),
                 "trim-right": _button("cutRight", "trim-right at playhead"),
                 "undo": _button("undo", "undo"), "redo": _button("redo", "redo"),
                 "marker": _button("mark", "marker added"), "zoomfit": _button("quicklyAdjustZoomFit", "zoom fit")})


@command("save")
def _save(args):
    press("cmd+s")
    time.sleep(1.5)
    return "saved"


@command("export")
def _export(args):
    export(flag(args, "--to"), flag(args, "--timeout", int, 900), toggle_sync="--toggle-sync" in args)


@command("play")
def _play(args):
    # The transport button is renamed by its state (PlayerPlayBtn while paused, PlayerPauseBtn while playing),
    # so take whichever is showing and the toggle lands either way round.
    click_on("PlayerPlayBtn" if find("PlayerPlayBtn") else "PlayerPauseBtn")


@command("playhead")
def _playhead(args):
    at, total = readout()
    return f"{at} / {total}"


@command("clips")
def _clips(args):
    list_clips()


@command("state")
def _state(args):
    timeline_state(flag(args, "--draft"))


@command("shot")
def _shot(args):
    return f"wrote {screenshot(args[0] if args else 'capcut.png')}"


# ---- looking around, for when a CapCut update moves the accessibility ids

@command("dump")
def _dump(args):
    for _, label, box in on_screen(args[0] if args else None):
        if label:
            where = f"  [{box[0]:.0f},{box[1]:.0f} {box[2]:.0f}x{box[3]:.0f}]" if box else ""
            print(f"{label}{where}")


@command("click")
def _click(args):
    return f"clicked: {click_on(args[0])}"


@command("clickxy")
def _clickxy(args):
    # An export or Link-media dialog is a QML overlay with nothing inside it for accessibility to see, so a
    # position is the only way to reach its controls.
    click(float(args[0]), float(args[1]), times=flag(args, "--clicks", int, 1))
    return f"clicked ({args[0]}, {args[1]})"


@command("key")
def _key(args):
    press(args[0])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(USAGE)
    name, args = sys.argv[1], sys.argv[2:]
    handler = COMMANDS.get(name)
    if handler is None:
        raise SystemExit(f"unknown command: {name}")
    said = handler(args)
    if said is not None:
        print(said)


if __name__ == "__main__":
    main()
