#!/usr/bin/env python3
"""test_capcut_live.py — the CapCut bridge's decisions, checked without CapCut, a screen or pyobjc.

workflows/capcut-live.py drives a real app, so its full behaviour is proven elsewhere against a recorded
fake CapCut. This pins the decisions inside it that each broke once:
  • `--track` picks tracks by what they hold. A VectCut-built draft carries flag 0 on every track, so a flag
    test found no text or overlay there and let `remove --track main` delete a caption or a sound.
  • `open` matches a draft's exact name ("Reel 1.1" double-clicked "Reel 1.12").
  • `replay` gives the draft a canvas shaped like the footage as it plays (an upright phone clip is 9:16).
  • `graphics` counts a graphic planned at 0 s and puts overlapping graphics on separate layers.
  • On Windows a draft write never force-kills CapCut (it refuses instead) and nothing calls osascript.
  • A write that stops part-way opens CapCut again if it was the bridge that closed it.
Run: python3 product/tests/test_capcut_live.py
"""
import importlib.util, json, os, subprocess, sys, tempfile, types
from pathlib import Path

for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try:
        if (getattr(_s, "encoding", "") or "").lower().replace("-", "") != "utf8":
            _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.name != "nt":   # the bridge imports the Mac accessibility frameworks at load; stand-ins keep it importable
    for mod, names in (("ApplicationServices", ["AXUIElementCopyAttributeValue", "AXUIElementCreateApplication",
                                                "AXValueGetValue", "kAXValueCGPointType", "kAXValueCGSizeType"]),
                       ("Quartz", ["CGEventCreateKeyboardEvent", "CGEventCreateMouseEvent", "CGEventPost",
                                   "CGEventSetFlags", "CGEventSetIntegerValueField", "kCGEventFlagMaskCommand",
                                   "kCGEventFlagMaskShift", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp",
                                   "kCGEventMouseMoved", "kCGHIDEventTap", "kCGMouseButtonLeft",
                                   "kCGMouseEventClickState"])):
        if mod not in sys.modules:
            m = types.ModuleType(mod)
            for n in names:
                setattr(m, n, (lambda *a, **k: None) if n[0] != "k" else 0)
            sys.modules[mod] = m
spec = importlib.util.spec_from_file_location("capcut_live", os.path.join(ENGINE, "workflows", "capcut-live.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def track(kind, flag, n, default=True):
    return {"type": kind, "flag": flag, "is_default_name": default, "segments": [{"i": i} for i in range(n)]}


# 1) --track by what a track holds
vectcut_tracks = [track("video", 0, 3, default=False), track("video", 0, 1), track("audio", 0, 7),
                  track("text", 0, 2), track("text", 0, 1)]
vectcut = {"tracks": vectcut_tracks}
check(bridge.role_tracks(vectcut, "main") == [vectcut_tracks[0]], "main must be the footage track only")
check(bridge.role_tracks(vectcut, "overlay") == [vectcut_tracks[1]], "overlay must be the other video track")
check(bridge.role_tracks(vectcut, "text") == vectcut_tracks[3:], "text must be both text tracks")
check([bridge.role_of(vectcut, t) for t in vectcut_tracks] == ["main", "overlay", "audio", "text", "text"],
      "state must label tracks the way --track names them")
native_tracks = [track("video", 0, 1, default=False), track("video", 2, 5), track("audio", 0, 2)]
check(bridge.main_track({"tracks": native_tracks}) is native_tracks[0], "a flag-2 overlay with more clips is still not main")

# 2) canvas shaped like the footage as it plays
for probed, rotation, want in (((3840, 2160, 1, True), -90, (1080, 1920)), ((1920, 1080, 1, True), 0, (1920, 1080)),
                               ((1080, 1920, 1, True), 0, (1080, 1920)), ((1728, 3072, 1, True), 0, (1080, 1920)),
                               ((2160, 3840, 1, True), 90, (1920, 1080)), ((0, 0, 1, True), 0, (1920, 1080))):
    got = bridge.canvas_for(probed, rotation)
    check(got == want, f"canvas for {probed[:2]} turned {rotation}: {got}, wanted {want}")

# 3) overlapping graphics go up a layer; touching ones share it
stacked = {"tracks": [track("video", 0, 1, default=False),
                      {"type": "video", "flag": 2, "segments": [{"target_timerange": {"start": 0, "duration": 2_000_000}}]}]}
check(bridge.free_layer(stacked, 1_000_000, 500_000) == 2, "an overlapping graphic must take the next layer")
check(bridge.free_layer(stacked, 2_000_000, 500_000) == 1, "a graphic that only touches may share the layer")
check(bridge.free_layer({"tracks": []}, 0, 1) == 1, "with no overlay tracks, layer 1")

# 4) open matches the exact name
tiles = [("e1", "HomePageDraftTitle:Reel 1.12", (0, 0, 10, 10)), ("e2", "HomePageDraftTitle:Reel 1.1", (20, 0, 10, 10))]
real_on_screen = bridge.on_screen
bridge.on_screen = lambda needle=None: [t for t in tiles if needle is None or needle.lower() in t[1].lower()]
hit = bridge.find_title("Reel 1.1")
check(hit is not None and hit[0] == "e2", f"open 'Reel 1.1' must pick that tile, got {hit}")
check(bridge.find_title("Reel 1") is None, "a partial name must not open the first draft that contains it")
bridge.on_screen = real_on_screen

# 5) a graphic planned at 0 s is placed; overlapping ones are given free layers
tmp = tempfile.mkdtemp(prefix="bridge-test-")
job = Path(tmp, "projects", "gfx")
(job / "assets").mkdir(parents=True)
for f in ("a.mov", "b.mov"):
    (job / "assets" / f).write_bytes(b"x")
with open(job / "graphics-plan.json", "w", encoding="utf-8") as fh:
    json.dump({"graphics": [{"file": "a.mov", "start": 0}, {"file": "b.mov", "t": 0.0, "start": None}]}, fh)
laid = []
real_repo, real_editing, real_lay = bridge.REPO, bridge.editing, bridge.lay_graphic
bridge.REPO = Path(tmp)
import contextlib


@contextlib.contextmanager
def fake_editing(name):
    yield {"tracks": []}, Path(tmp)


bridge.editing = fake_editing
bridge.lay_graphic = lambda d, folder, media, at_us, layer, length_us=None: laid.append((Path(media).name, at_us, layer))
try:
    bridge.place_plan("Draft", "gfx")
finally:
    bridge.REPO, bridge.editing, bridge.lay_graphic = real_repo, real_editing, real_lay
check(laid == [("a.mov", 0, None), ("b.mov", 0, None)], f"graphics at 0 s must be placed, each on a free layer: {laid}")

# 6) Windows: no osascript, and a write refuses instead of killing CapCut
os.environ.pop("CAPCUT_ALLOW_OPEN", None)
ran = []
real_run = subprocess.run
subprocess.run = lambda args, *a, **k: ran.append(list(args)) or subprocess.CompletedProcess(args, 0, "", "")
real_win = bridge.ON_WINDOWS
real_running = bridge._ds.capcut_running
try:
    bridge.ON_WINDOWS = True
    bridge.tell_capcut("activate")
    check(not any(r[0] == "osascript" for r in ran), "on Windows nothing may call osascript")
    bridge._ds.capcut_running = lambda: True
    try:
        bridge.close_for_write("change this draft")
        check(False, "on Windows a write with CapCut open must refuse")
    except bridge._ds.CapCutOpen:
        pass
    check(not any(r[0] == "taskkill" for r in ran), f"on Windows a write must never kill CapCut: {ran}")
finally:
    subprocess.run = real_run
    bridge.ON_WINDOWS = real_win
    bridge._ds.capcut_running = real_running

# 7) a write that stops part-way gives her CapCut back (Mac: the bridge closed it, so it opens it again)
folder = Path(tmp, "Draft")
folder.mkdir()
with open(bridge._ds.draft_json(str(folder)), "w", encoding="utf-8") as fh:
    json.dump({"tracks": [], "duration": 0}, fh)
events = []
saved = (bridge.existing_draft, bridge.capcut_pid, bridge.quit_capcut, bridge.start_capcut, bridge.ON_WINDOWS,
         bridge._ds.require_capcut_quit)
bridge.existing_draft = lambda name: folder
bridge.capcut_pid = lambda: 4321
bridge.quit_capcut = lambda timeout=20: events.append("quit")
bridge.start_capcut = lambda: events.append("start")
bridge.ON_WINDOWS = False
bridge._ds.require_capcut_quit = lambda action="": None
try:
    with bridge.editing("Draft") as (_d, _f):
        raise SystemExit("that overlay is already on the timeline")
except SystemExit:
    pass
finally:
    (bridge.existing_draft, bridge.capcut_pid, bridge.quit_capcut, bridge.start_capcut, bridge.ON_WINDOWS,
     bridge._ds.require_capcut_quit) = saved
check(events == ["quit", "start"], f"a refused edit must reopen the CapCut it closed: {events}")

if failures:
    print("✗ capcut bridge: " + "; ".join(failures))
    sys.exit(1)
print("✓ capcut bridge: --track picks by what a track holds, open matches the exact name, the canvas follows the "
      "footage, graphics at 0 s and overlapping ones are placed, Windows never kills CapCut or calls osascript, "
      "and a refused edit reopens CapCut")
