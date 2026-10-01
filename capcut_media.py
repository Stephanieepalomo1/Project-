#!/usr/bin/env python3
"""capcut_media.py — MEDIA GUARDRAIL for CapCut drafts.

Guarantees every clip on the timeline will LINK and IMPORT in CapCut. The failure this prevents: media
placed by referencing an external absolute path shows as "not linked" and never appears in the media
panel, because CapCut only auto-registers media that lives INSIDE the draft folder — and a ProRes 4444
overlay triggers "couldn't import some of the files". Both silently ship a broken reel.

So, for every clip a build puts on the timeline this makes sure it is:
  1. PROJECT-LOCAL  — copied into the draft's own `assets/video` | `assets/audio` and referenced by the
     draft placeholder path (never an external absolute path). A byte copy, NEVER a re-encode, so
     source footage color is untouched.
  2. REGISTERED     — has an entry in `draft_meta_info.json` so CapCut links it and lists it.
  3. VALID DURATION — a zero/absent duration reads as "-" and won't play; probe + set it.
  4. IMPORTABLE     — an OPAQUE clip must be an H.264/HEVC MP4 (a big opaque ProRes is what "couldn't
     import"). A TRANSPARENT overlay is the one exception: render it as ProRes 4444 with alpha (yuva) —
     CapCut imports that fine once it is registered (this is how the reel's Claude-UI overlay ships).

`ensure_shippable(d, draft_dir)` mutates the loaded draft_info dict + writes draft_meta_info, and RETURNS
a list of unfixable problems (empty == shippable) so the caller can refuse the build. Whitelabel-clean:
operates only on the draft dir + media handed to it; no personal names or paths.
"""
import os, time, json, shutil, subprocess, re, time
from capcut_ripple import enforce_maintrack_ripple   # re-assert the main-track magnet on any draft we re-save

import sys as _sys, os as _os_ds
for _s in (_sys.stdout, _sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
DEFAULT_TOKEN = "0E685133-18CE-45ED-8CB8-2904A212EC80"   # pyJianYingDraft draft-path placeholder
# Opaque ProRes -> "couldn't import" (re-export MP4). ProRes 4444 WITH alpha (yuva) is allowed: it is the
# CapCut transparent-overlay format and imports once registered. See has_alpha() + the codec gate below.

def _out(*a): return subprocess.run(a, capture_output=True, text=True).stdout.strip()

def probe_video(path):
    """-> (duration_us, width, height, codec_name, pix_fmt)."""
    j = _out("ffprobe","-v","error","-select_streams","v:0","-show_entries",
             "stream=codec_name,width,height,pix_fmt:format=duration","-of","json",path)
    try:
        o = json.loads(j); st = (o.get("streams") or [{}])[0]
        dur = float(o.get("format",{}).get("duration") or 0)
        return (int(round(dur*1e6)), int(st.get("width") or 0), int(st.get("height") or 0),
                (st.get("codec_name") or ""), (st.get("pix_fmt") or ""))
    except Exception:
        return 0,0,0,"",""

def has_alpha(pix_fmt):
    p = (pix_fmt or "").lower()
    return p.startswith("yuva") or p.startswith("ya") or "rgba" in p or "argb" in p or "bgra" in p or "abgr" in p

def probe_dur_us(path):
    v = _out("ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path)
    try: return int(round(float(v)*1e6))
    except Exception: return 0

def token_of(d):
    for m in d["materials"].get("videos",[]) + d["materials"].get("audios",[]):
        mm = re.search(r"##_draftpath_placeholder_([0-9A-Za-z-]+)_##", m.get("path","") or "")
        if mm: return mm.group(1)
    return DEFAULT_TOKEN

def real_path(path, draft_dir, token):
    ph = f"##_draftpath_placeholder_{token}_##"
    return path.replace(ph, draft_dir) if path and path.startswith("##") else (path or "")

def write_cover(d, draft_dir):
    """Generate the draft's cover thumbnail (draft_dir/draft_cover.jpg). CapCut's drafts list points every
    entry at a draft_cover.jpg; finalize() names that file in the registry but nothing was CREATING it, so a
    fresh build had a cover path aimed at a file that never existed — one of the two reasons a new draft
    could be INVISIBLE in the drafts grid with no error. Grab one frame from the first footage clip, sized
    to the 1080x1920 JPG the app expects. Best-effort: returns True on success, False if it can't (never
    raises — a missing cover must not fail an otherwise-good build). Whitelabel-clean: only the draft dir."""
    try:
        token = token_of(d)
        vids = [t for t in d.get("tracks", []) if t.get("type") == "video" and t.get("segments")]
        if not vids:
            return False
        foot = max(vids, key=lambda t: len(t["segments"]))
        seg0 = foot["segments"][0]
        mid = seg0.get("material_id")
        mat = next((m for m in d["materials"].get("videos", []) if m.get("id") == mid), None)
        if not mat:
            return False
        src = real_path(mat.get("path", ""), draft_dir, token)
        if not src or not os.path.isfile(src):
            return False
        # a few seconds into the kept portion (clamped small so a short first clip still yields a frame)
        ss = max(0.0, seg0.get("source_timerange", {}).get("start", 0) / 1_000_000) + 0.5
        out = os.path.join(draft_dir, "draft_cover.jpg")
        subprocess.run(["ffmpeg", "-y", "-ss", f"{ss:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                        out], capture_output=True, text=True)
        return os.path.isfile(out) and os.path.getsize(out) > 0
    except Exception:
        return False

# A REAL, captured CapCut registry-entry shape (root_meta_info.json -> all_draft_store[i]),
# with every per-draft + machine/cloud-identifying value neutralized. Used ONLY as the template
# for a NEW entry when the registry is empty (brand-new CapCut install: all_draft_store == []).
# Captured field-for-field from a real CapCut-written registry (not hand-guessed) so a fresh
# buyer's first-ever draft registers with the exact shape CapCut's drafts grid expects.
# register_draft() overwrites the identifying fields (name/paths/ids/timestamps/duration) anyway;
# this only supplies the SHAPE + the cloud/pippit defaults CapCut fills in itself.
_EMPTY_REGISTRY_ENTRY = {
    "cloud_draft_cover": False, "cloud_draft_sync": False,
    "draft_cloud_last_action_download": False, "draft_cloud_purchase_info": "",
    "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
    "draft_cloud_videocut_purchase_info": "", "draft_cover": "", "draft_fold_path": "",
    "draft_id": "", "draft_is_ai_shorts": False, "draft_is_cloud_temp_draft": False,
    "draft_is_infinite_canvas_draft": False, "draft_is_invisible": False,
    "draft_is_pippit_draft": False, "draft_is_web_article_video": False, "draft_json_file": "",
    "draft_name": "", "draft_new_version": "", "draft_root_path": "",
    "draft_timeline_materials_size": 0, "draft_type": "", "draft_web_article_video_enter_from": "",
    "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
    "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "",
    "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0,
    "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
    "tm_draft_cloud_user_id": -1, "tm_draft_create": 0, "tm_draft_modified": 0,
    "tm_draft_removed": 0, "tm_duration": 0,
}


def register_draft(cap, name, draft_dir, draft_json_file, draft_id, duration, now, us=1_000_000):
    """Insert/replace this draft's entry in CapCut's root_meta_info.json — the registry the drafts GRID
    reads to list, sort, and cover every draft. Shared by cleanyap.py + superyap.py finalize().

    On a brand-new CapCut install `all_draft_store` is `[]`, so the old `all_draft_store[0]` clone
    raised IndexError and crashed the buyer's FIRST-EVER build. Fall back to the real-schema template
    above when the store is empty; clone an existing entry's shape when it isn't (unchanged behavior).
    `now` is threaded in from the caller (not computed here) so it MATCHES the timestamp already stamped
    into the sibling draft_meta_info.json write — CapCut sorts the grid off both and they must agree."""
    rp = f"{cap}/root_meta_info.json"
    started = False
    try:
        r = json.load(open(rp, encoding="utf-8"))
    except FileNotFoundError:
        # A CapCut that has never been opened has not written its list yet. That is an empty list, not an error:
        # raising here came AFTER finalize had renamed the draft into place, so the build failed and the
        # unregistered folder kept the name, and the next build to that name was refused. Start the list in
        # the shape CapCut writes it (the drafts, how many, and where they live).
        os.makedirs(cap, exist_ok=True)
        r, started = {"all_draft_store": [], "draft_ids": 0, "root_path": cap}, True
    store = r.get("all_draft_store") or []
    tmpl = store[0] if store else _EMPTY_REGISTRY_ENTRY
    e = dict(tmpl)
    e.update(
        draft_name=name, draft_fold_path=draft_dir, draft_id=draft_id, draft_json_file=draft_json_file,
        draft_root_path=cap, draft_cover=f"{draft_dir}/draft_cover.jpg",
        tm_draft_create=now * us, tm_draft_modified=now * us, tm_draft_removed=0, tm_duration=duration)
    r["all_draft_store"] = [x for x in store if x.get("draft_name") != name]
    r["all_draft_store"].insert(0, e)
    if started:                                   # a list this started: count the draft it now holds
        r["draft_ids"] = len(r["all_draft_store"])
    json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)

    # AND KEEP IT AT THE TOP — permanently, for every caller (locked 2026-09-19, creator: "when you make
    # something for me in CapCut, it always needs to be at the top ... I do not want to go hunting for your
    # drafts, and I always am").
    #
    # The insert(0) above only wins until CapCut's NEXT session: CapCut rebuilds this file from its own
    # records and re-sorts by tm_draft_modified, so a draft placed at the top while CapCut was quit sinks
    # back into a 160+ deep list the moment she opens the app. That is the hunting. capcut_front owns the
    # durable answer (a remembered pin its LaunchAgent re-applies after every session).
    #
    # It lives HERE, in register_draft, and NOT in each builder's finalize, because this is the single
    # chokepoint every draft passes through to become visible in CapCut at all. Wiring it per-builder means
    # the next build path that gets written forgets it, and she goes hunting again. Registering a draft and
    # putting it on top are one action now, and cannot come apart.
    #
    # Never fatal: a draft that built fine must not fail because the list could not be reordered.
    try:
        import capcut_front
        capcut_front.remember(name)
        capcut_front.ensure()
    except Exception as _e:
        print(f"  \u26a0 built and registered, but could not pin it to the top of the list "
              f"({type(_e).__name__}). Run: python3 product/capcut_front.py \"{name}\"")


def _used_ids(d):
    ids = set()
    for t in d["tracks"]:
        for s in t.get("segments",[]):
            ids.add(s.get("material_id"))
    return ids

def _register(draft_dir, mat_id, rel_path, metetype, dur_us, w, h, name):
    """Add or refresh the draft_meta_info entry so CapCut links + shows the clip."""
    mp = f"{draft_dir}/draft_meta_info.json"
    meta = json.load(open(mp, encoding="utf-8"))
    grp = None
    for g in meta.get("draft_materials", []):
        if isinstance(g, dict) and isinstance(g.get("value"), list) and g.get("type", 0) == 0:
            grp = g; break
    if grp is None:
        grp = {"type": 0, "value": []}; meta.setdefault("draft_materials", []).append(grp)
    now = int(time.time())
    fields = dict(ai_group_type="", create_time=now, duration=dur_us, enter_from=0, extra_info=name,
                  file_Path=rel_path, height=h, id=mat_id, import_time=now, import_time_ms=now*1000000,
                  item_source=1, material_color_tag="", md5="", metetype=metetype,
                  roughcut_time_range={"duration": dur_us, "start": 0},
                  sub_time_range={"duration": -1, "start": -1}, type=0, width=w)
    existing = next((it for it in grp["value"] if it.get("id") == mat_id), None)
    if existing: existing.update(fields)
    else: grp["value"].append(fields)
    json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)

def ensure_shippable(d, draft_dir, token=None):
    """Make every timeline clip link + import, or return the reasons it can't. Mutates d (localizes +
    repaths + fixes durations) and writes draft_meta_info registrations. Empty list == shippable."""
    token = token or token_of(d)
    used = _used_ids(d)
    problems = []
    for kind, pool, metetype in (("video","videos","video"), ("audio","audios","music")):
        for m in d["materials"].get(pool, []):
            if m.get("id") not in used: continue
            rp = real_path(m.get("path",""), draft_dir, token)
            if not rp or not os.path.exists(rp):
                problems.append(f"{metetype} '{os.path.basename(m.get('path','') or m['id'])}' file missing: {rp}")
                continue
            if kind == "video":
                dur_us, w, h, codec, pix = probe_video(rp)
                # ProRes is only valid as a TRANSPARENT overlay (ProRes 4444, alpha/yuva) — CapCut imports
                # that when it's registered. Opaque ProRes must be an MP4 (a big opaque ProRes is what "couldn't
                # import"). So refuse ProRes ONLY when it carries no alpha.
                if "prores" in codec.lower() and not has_alpha(pix):
                    problems.append(f"video '{os.path.basename(rp)}' is opaque ProRes ({pix}) — re-export as an "
                                    f"H.264/HEVC MP4 (ProRes is only for transparent overlays: ProRes 4444/yuva)")
                    continue
            else:
                dur_us, w, h = probe_dur_us(rp), 0, 0
            # 1) project-local
            sub = "video" if kind == "video" else "audio"
            local = f"{draft_dir}/assets/{sub}/{os.path.basename(rp)}"
            if os.path.abspath(rp) != os.path.abspath(local):
                os.makedirs(os.path.dirname(local), exist_ok=True)
                if not os.path.exists(local) or os.path.getsize(local) != os.path.getsize(rp):
                    shutil.copy2(rp, local)
                m["path"] = f"##_draftpath_placeholder_{token}_##/assets/{sub}/{os.path.basename(rp)}"
            # 3) valid duration + dims
            if not m.get("duration"): m["duration"] = dur_us
            if kind == "video":
                if w and not m.get("width"):  m["width"]  = w
                if h and not m.get("height"): m["height"] = h
            # 2) register
            _register(draft_dir, m["id"], f"./assets/{sub}/{os.path.basename(rp)}", metetype,
                      m.get("duration") or dur_us, m.get("width") or w, m.get("height") or h,
                      os.path.basename(rp))
    return problems

def harden_draft(draft, fix=True):
    """Standalone entry: run the guardrail on a finished draft folder (or draft name under the default
    CapCut projects dir). Loads draft_info, ensures shippable, saves. Returns problems. CapCut must be quit."""
    if os.path.isdir(draft):
        D = draft
    else:
        _cap_root = (os.path.join(os.environ["LOCALAPPDATA"], "CapCut/User Data/Projects/com.lveditor.draft").replace("\\", "/")
                     if os.name == "nt" else
                     os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft"))
        D = os.path.join(_cap_root, draft)
    if os.name == "nt":
        _running = "CapCut.exe" in subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    else:
        _running = subprocess.run(["pgrep","-f","CapCut.app/Contents/MacOS/CapCut"], capture_output=True).returncode == 0
    if _running:
        raise SystemExit("CapCut is open — quit it first (editing draft JSON while open gets clobbered).")
    p = _ds.draft_json(D); d = json.load(open(p, encoding="utf-8"))
    problems = ensure_shippable(d, D)
    if fix:
        enforce_maintrack_ripple(d)   # a re-saved draft must never ship a dead magnet — re-anchor before writing
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return problems, D

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python capcut_media.py \"<Draft Name>\" | <draft_dir>"); raise SystemExit(2)
    probs, D = harden_draft(sys.argv[1])
    if probs:
        print("✗ NOT shippable — media that won't link/import:")
        for pr in probs: print("   -", pr)
        raise SystemExit(1)
    print(f"✓ shippable — every clip is project-local, registered, valid, and importable\n  {D}")
