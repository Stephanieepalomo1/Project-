#!/usr/bin/env python3
"""spoken_cues.py — when a line SAYS the effect, build that effect on that line.

The creator can direct the edit from inside the footage: "this is where the hook goes", "this line is a
karaoke caption", "and this is a full-screen takeover". Each of those is a spoken instruction naming a
treatment the rendered engine already ships. This reads the cut transcript, finds every line that names
one, and writes the caption plan that puts exactly that treatment on exactly that line, at the line's real
timing. Nothing is invented: no copy she did not say, no effect she did not name.

Two uses, one mechanism:
  - the FIRST-REEL SCRIPT (product/FIRST-REEL-SCRIPT.md): a short script where every line is a cue, so a
    buyer's first build shows the whole effects menu on her own face in one short, fast run.
  - the standing tip: any reel can carry a cue line or two ("here's a count-up, three hundred dollars").

What a cue is. A sentence that names an effect (the vocabulary words in product/BUILD-VOCABULARY.md) AND
points at itself ("this is", "here's", "this line", "now", "watch"). The pointing requirement is what keeps
an ordinary sentence that happens to contain "hook" or "star" from being read as an instruction.

  python3 product/spoken_cues.py <job>              # report the cues it heard (writes nothing)
  python3 product/spoken_cues.py <job> --write      # write projects/<job>/caption-plan.json
  python3 product/spoken_cues.py <job> --write --force   # replace an existing plan (it is backed up first)

Placement is measured, never typed: star / count-up / bubble positions come from the job's
subject-zones.json (run `uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4` first). Without
it the tool refuses to place them rather than guess, and says so.

The plan is a STARTING plan for the plan-approve-build rule, not a bypass of it: show the creator the cue
table, get the one approval, then build through the normal well-done / medium path.
"""
import argparse, datetime, importlib.util, json, os, re, shutil, sys, unicodedata

for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# Sentence splitting has ONE home (the graphics-plan segmenter). Load it rather than keep a second copy.
_seg_path = os.path.join(ROOT, ".claude", "skills", "graphics-plan", "scripts", "beat-lines.py")
_spec = importlib.util.spec_from_file_location("beat_lines", _seg_path)
seg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(seg)

# A cue has to point at itself. "this is a takeover" is a cue; "my kids took over the kitchen" is not.
POINTER = re.compile(r"\b(this|here'?s|here is|here are|these|that's|now|watch|down here|up here)\b")

# effect id -> (pattern that names it, what the creator reads in the report)
VOCAB = [
    ("hook",      re.compile(r"\bhook\b"),                          "hook card up top"),
    ("karaoke",   re.compile(r"\bkaraoke\b"),                       "karaoke caption on this line"),
    ("single",    re.compile(r"\bsingle[- ]?word\b|\bone word at a time\b"), "single-word captions"),
    ("takeover",  re.compile(r"\btake ?over\b"),                    "full-screen takeover"),
    ("counter",   re.compile(r"\bcount[- ]?up\b"),                  "count-up card"),
    ("punch",     re.compile(r"\bpunch[- ]?in\b"),                  "punch-in zoom on this line"),
    ("star",      re.compile(r"\bstars?\b"),                        "star pop"),
    ("bubble",    re.compile(r"\bthought bubble\b"),                "thought bubble"),
    ("breakaway", re.compile(r"\bbreak(s|ing)? ?away\b"),           "breakaway card"),
]

# The sound that voices each motion, trimmed to that motion's length. Names resolve through the bundled
# library (python3 product/capcut_sfx.py --list); build-reel-mp4.py auto-levels every cue under the voice.
SFX = {
    "hook":      ("whoosh-short", 0.40),
    "karaoke":   ("click-soft",   0.15),
    "takeover":  ("pop-whoosh",   0.45),
    "counter":   ("coin-earn",    0.60),
    "punch":     ("pop",          0.18),
    "star":      ("cute_pop",     0.30),
    "bubble":    ("pop",          0.18),
    "breakaway": ("whoosh",       0.50),
}

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
             "thousand": 1000}


_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})


def norm_word(w):
    """Match build-reel-type.py's norm() exactly: the plan's phrases must equal its token stream. Case folded,
    typographic apostrophes made plain, then letters, digits and the apostrophe kept, in ANY script (the
    builder's matcher learned that, and a copy that still kept a-z alone could never match an accented cue)."""
    w = unicodedata.normalize("NFKC", str(w)).translate(_APOSTROPHES).casefold()
    return "".join(c for c in w if c == "'" or unicodedata.category(c)[0] in "LMN")


def line_text(run):
    return " ".join(str(w["text"]).strip() for w in run).strip()


def phrase(run):
    """The line as build-reel-type.py will see it, so the plan can never be 'stale vs the cut' on day one."""
    return " ".join(t for t in (norm_word(str(w["text"])) for w in run) if t)


# A LIST of effects asked for in one breath: "I want to see a hook above my head, single word captions under
# my chin, a line of karaoke captions, a full screen takeover, and then a count up." No clause points at itself,
# so the pointer rule above never fires, yet every clause names an effect on the words she is saying. A list
# only counts after an explicit request, and inside one an effect has to be named unmistakably ("takeover" or
# "full screen", never "take over"; no stars), so ordinary talk ("my kids took over the kitchen") stays talk.
REQUEST = [r.split() for r in ("i want to see", "i wanna see", "i want", "i'd like", "i would like", "give me",
                               "show me", "let's see", "let's add", "let's do", "can you add", "can we add",
                               "can we do", "can we get", "add")]
LIST_VOCAB = [(eid, pat, label) for eid, pat, label in VOCAB if eid not in ("star", "takeover")]
LIST_VOCAB.insert(3, ("takeover", re.compile(r"\btakeover\b|\bfull[- ]?screen\b"), "full-screen takeover"))
_LEAD = {"a", "an", "the", "some", "and", "then", "also", "plus"}


def _request_end(toks):
    """Index just past the first request phrase in a clause's tokens, or None."""
    for i in range(len(toks)):
        for req in REQUEST:
            if toks[i:i + len(req)] == req:
                return i + len(req)
    return None


def _list_cues(run):
    """[(effect, clause run, label), ...] for a sentence that asks for effects as a list, else []."""
    toks = [norm_word(str(w["text"])) for w in run]
    start = _request_end(toks)
    if start is None:
        return []
    clauses, cur = [], []
    for w, t in list(zip(run, toks))[start:]:
        if t == "and" and cur:
            clauses.append(cur); cur = []
        cur.append(w)
        if str(w["text"]).rstrip().endswith((",", ";")):
            clauses.append(cur); cur = []
    if cur:
        clauses.append(cur)
    found = []
    for clause in clauses:
        while clause and norm_word(str(clause[0]["text"])) in _LEAD:
            clause = clause[1:]
        low = line_text(clause).lower().replace("’", "'")
        for eid, pat, label in LIST_VOCAB:
            if clause and pat.search(low):
                found.append((eid, clause, label))
                break
    return found


def detect(words):
    """[(effect, run, label), ...] in spoken order. A line that points at itself: the first effect it names.
    A sentence that asks for a list of effects: one per clause that names one."""
    found, runs, skip = [], list(seg.sentences_from(words)), set()
    for i, run in enumerate(runs):
        if i in skip:
            continue
        low = line_text(run).lower().replace("’", "'")
        if not POINTER.search(low):
            found.extend(_list_cues(run))
            continue
        for eid, pat, label in VOCAB:
            if pat.search(low):
                # "Here's a count-up. Three hundred dollars." -- the number is often its own sentence
                if eid == "counter" and amount(low) is None and i + 1 < len(runs) \
                        and amount(line_text(runs[i + 1])) is not None:
                    run = run + runs[i + 1]; skip.add(i + 1)
                found.append((eid, run, label))
                break
    return found


def amount(text):
    """The number a count-up line names. '$300' -> 300; 'three hundred dollars' -> 300; none -> None."""
    m = re.search(r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?", text, re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        return v * 1000 if m.group(2) else v
    total, cur = 0, 0
    for tok in re.findall(r"[a-z]+", text.lower()):
        if tok not in NUM_WORDS: continue
        n = NUM_WORDS[tok]
        if n in (100, 1000): cur = max(cur, 1) * n
        else: cur += n
        if n == 1000: total += cur; cur = 0
    return (total + cur) or None


def zones_for(job_dir):
    p = os.path.join(job_dir, "subject-zones.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def open_spot(zones, want_h):
    """A y (px) with want_h of room below her, else above her. None if neither zone has the room."""
    z = zones["zones"]
    for name in ("below", "above"):
        b = z.get(name) or {}
        if b.get("usable") and (b["bottom"] - b["top"]) >= want_h:
            # sit low in the zone: the caption band rides the upper part of `below`
            return (b["bottom"] - want_h / 2 - 20) if name == "below" else (b["top"] + b["bottom"]) / 2
    return None


def build_plan(job, words, cues, zones):
    t0, t1 = float(words[0]["start"]), float(words[-1]["end"])
    plan = {
        "_doc": f"{job}: built from SPOKEN CUES (product/spoken_cues.py). Each line that names an effect gets "
                f"that effect, on that line, at its real timing. Starting plan: approve it, then build.",
        "register": "teaching",
        "spoken_cues": True,
        "duration": round(t1 + 0.6, 3),
        "caption_mode": "single",
        "caption_treatments": [],
        "takeover_keys": [], "takeover_exact": True, "takeover_hold": 0.6,
        "elements": [], "breakaways": [],
        "punch": {"scale": 1.10, "windows": []},
        "sfx": [],
    }
    notes, skipped = [], []
    W, H = 1080.0, 1920.0
    starts = [float(r[0]["start"]) for _e, r, _l in cues]
    for n, (eid, run, label) in enumerate(cues):
        a, b = float(run[0]["start"]), float(run[-1]["end"])
        # every effect clears before the next cue's effect arrives: two effects never share a beat
        nxt = starts[n + 1] if n + 1 < len(starts) else t1 + 2.0
        clear = nxt - 0.1
        said = line_text(run)
        if eid == "hook":
            plan["hook"] = [said.rstrip(".!?")]
            plan["hook_end"] = round(b + 1.2, 3)
        elif eid in ("karaoke", "single"):
            plan["caption_treatments"].append({"text": phrase(run), "mode": eid})
        elif eid == "takeover":
            plan["takeover_keys"].append(phrase(run))
            plan["takeover_hold"] = round(max(0.15, min(plan["takeover_hold"], clear - b)), 3)
        elif eid == "punch":
            plan["punch"]["windows"].append([round(a, 3), round(b, 3)])
        elif eid == "breakaway":
            plan["breakaways"].append({"at": round(a, 3), "out": round(min(b + 0.4, clear), 3),
                                       "lines": ["breakaway", "card"], "emphasis": "card"})
        elif eid in ("counter", "star", "bubble"):
            if not zones:
                skipped.append((eid, said, "her footage has not been measured yet, so there is no measured "
                                           "spot to put it. Run workflows/subject-zones.py, then run this again"))
                continue
            if eid == "counter":
                to = amount(said)
                if to is None:
                    skipped.append((eid, said, "the line names a count-up but no number to count to"))
                    continue
                y = open_spot(zones, 300)
                if y is None:
                    skipped.append((eid, said, "no open zone has room for the card on this framing")); continue
                plan["elements"].append({"kind": "counter", "at": round(a, 3), "duration": round(max(0.8, min(b + 0.8, clear) - a), 3),
                                         "x": 0.5, "y": round(y / H, 4), "w": 0.63, "from": 0, "to": to,
                                         "prefix": "$" if re.search(r"\$|dollar", said, re.I) else "",
                                         "count_duration": round(max(0.8, min(1.6, b - a)), 2)})
            elif eid == "star":
                side = zones.get("roomier_side", "right")
                sz = zones["zones"].get(side) or {}
                face = zones.get("face") or zones.get("subject") or {}
                x = sz.get("center_x_px", 900 if side == "right" else 180)
                y = (face.get("top", 700) + face.get("bottom", 1000)) / 2
                plan["elements"].append({"kind": "star", "at": round(a, 3), "duration": round(max(0.8, min(b + 1.0, clear) - a), 3),
                                         "x": round(x / W, 4), "y": round(y / H, 4), "size": 0.09, "rotate": 12})
            elif eid == "bubble":
                if "vibe" in plan:
                    skipped.append((eid, said, "one thought bubble per reel on the rendered route; kept the first"))
                    continue
                y = open_spot(zones, 160)
                if y is None:
                    skipped.append((eid, said, "no open zone has room for the bubble on this framing")); continue
                plan["vibe"] = {"kind": "bubble", "text": "💭 thought bubble", "x": 0.5,
                                "y": round(y / H, 4), "at": round(a, 3),
                                "out": round(max(a + 0.8, min(b + 1.5, clear)), 3)}
        f, trim = SFX.get(eid, (None, 0))
        if f:
            at = b - trim if eid == "counter" else a      # the coin lands when the count does
            plan["sfx"].append({"file": f, "at": round(max(0.0, at), 3), "trim": trim, "_why": f"voices the {label}"})
        notes.append((eid, a, b, said, label))
    # tidy: drop empty keys so the plan reads like a hand-written one
    for k in ("caption_treatments", "takeover_keys", "elements", "breakaways", "sfx"):
        if not plan[k]: plan.pop(k)
    if not plan["punch"]["windows"]: plan.pop("punch")
    if "takeover_keys" not in plan:
        plan.pop("takeover_exact"); plan.pop("takeover_hold")
    return plan, notes, skipped


def report(job, notes, skipped, heard_lines):
    out = [f"Spoken cues in {job}: {len(notes)} line(s) name an effect.", ""]
    out.append("| # | time | what she said | builds |")
    out.append("|---|------|---------------|--------|")
    for i, (eid, a, b, said, label) in enumerate(notes, 1):
        out.append(f"| {i} | {a:.1f}–{b:.1f}s | {said} | {label} |")
    if skipped:
        out.append("")
        out.append("Heard but not placed:")
        for eid, said, why in skipped:
            out.append(f"- \"{said}\": {why}.")
    if heard_lines is not None and heard_lines == 0:
        out.append("")
        out.append("No cue lines heard. This reel plans the normal way (graphics-plan).")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job")
    ap.add_argument("--write", action="store_true", help="write projects/<job>/caption-plan.json")
    ap.add_argument("--force", action="store_true", help="replace an existing caption-plan.json (backed up)")
    ap.add_argument("--json", action="store_true", help="print the plan instead of the report")
    args = ap.parse_args()

    job_dir = os.path.join(ROOT, "projects", args.job)
    words = seg.spoken_words(seg.locate_transcript(job_dir))
    cues = detect(words)
    zones = zones_for(job_dir)
    plan, notes, skipped = build_plan(args.job, words, cues, zones)
    print(json.dumps(plan, indent=1, ensure_ascii=False) if args.json else report(args.job, notes, skipped, len(cues)))
    if not cues:
        return 3
    if args.write:
        dest = os.path.join(job_dir, "caption-plan.json")
        if os.path.exists(dest):
            if not args.force:
                print(f"\ncaption-plan.json already exists for {args.job}; left it alone. "
                      f"Add --force to replace it (the old one is kept as a dated backup).")
                return 2
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(dest, f"{dest}.{stamp}.bak")
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1, ensure_ascii=False)
        print(f"\nWrote {os.path.relpath(dest, ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
