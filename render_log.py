#!/usr/bin/env python3
"""render_log.py — every slow step leaves a record of how far it got, even when it is stopped.

    python3 product/render_log.py          # the last few slow steps, in plain words

WHY THIS EXISTS. A buyer's well-done render was still going the next morning, so it was cancelled, and
nothing on the machine could say what it had been doing. The timing file (render-diagnostics.json) is
written when a render ENDS, and a cancelled render never ends. The stall report only fires when the
renderer goes silent, and a render that is crawling is not silent. So the one question support needed
answered, "was it frozen, or slow, and how slow", had no answer anywhere, and the only honest reply was
a guess.

WHAT IT KEEPS. One small JSON per slow step in _local/render-log/ (buyer-local, never shipped, never
sent): which step, which composition, when it started, how many frames it had done out of how many,
when the renderer last printed anything, and how it ended. It is rewritten every few seconds while the
step runs, so a step that is killed mid-way still says how far it got and when it last showed a sign of
life. Two timestamps do the diagnosing:
    last_output_at  the renderer last printed something (a frame count, a phase)
    written_at      this record was last rewritten (the engine was still alive and waiting)
A render that stops printing while the engine keeps waiting FROZE. One that keeps printing frames at a
slow rate CRAWLED. One whose record stops being rewritten was STOPPED from outside (cancelled, closed,
restarted). Records whose times overlap RAN AT THE SAME TIME, which on its own slows both to a crawl.
/report-a-problem reads these; nothing else needs to.

Report-only data: the step, the composition folder, frame counts and times. No content, no footage.
Never raises: a record that fails to write must never take down the render it describes.
"""
import glob, json, os, sys, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "_local", "render-log")
KEEP = 20          # records kept; older ones are pruned when a new step starts
EVERY = 10         # seconds between rewrites while a step runs
ALIVE = 60         # a record rewritten this recently belongs to a step that is still running
FROZE = 600        # renderer silent this long while the engine waited = frozen, not slow


def _short(path):
    """Relative to the engine when inside it, ~ for the home folder, so a paste never carries a name."""
    if not path:
        return None
    try:
        p = os.path.abspath(path)
        if p.startswith(ROOT + os.sep):
            return os.path.relpath(p, ROOT).replace(os.sep, "/")
        home = os.path.expanduser("~")
        return p.replace(home, "~", 1) if home and home != os.sep else p
    except Exception:   # noqa: BLE001
        return str(path)


def _prune():
    try:
        files = sorted(glob.glob(os.path.join(LOG_DIR, "*.json")))
        for f in files[:-KEEP]:
            os.remove(f)
    except Exception:   # noqa: BLE001
        pass


class Trail:
    """One slow step's record. Start it right before the step, call output() whenever the step prints
    progress, finish() when it ends. A heartbeat thread rewrites it every EVERY seconds on its own, so
    even a step that prints nothing (an ffmpeg bake) shows how long it was alive."""

    def __init__(self, step, target=None, reports_progress=True):
        """reports_progress=False for a step that prints nothing while it works (an ffmpeg bake run at
        -loglevel error), so its silence is never read as a freeze."""
        now = time.time()
        self.rec = {"step": step, "target": _short(target), "pid": os.getpid(),
                    "reports_progress": bool(reports_progress),
                    "platform": sys.platform, "cores": os.cpu_count(),
                    "started_at": now, "written_at": now, "last_output_at": None,
                    "first_frame_at": None, "frames_done": None, "frames_total": None,
                    "phase": "", "stall_seconds": None, "finished_at": None, "result": "running",
                    "facts": {}}
        self.path = os.path.join(LOG_DIR, time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
                                 + f"-{os.getpid()}-{id(self) % 10000:04d}.json")
        self._lock = threading.RLock()
        self._done = threading.Event()
        self._last_write = 0.0
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            _prune()
        except Exception:   # noqa: BLE001
            pass
        self._write()
        threading.Thread(target=self._beat, daemon=True).start()

    def _beat(self):
        while not self._done.wait(EVERY):
            self._write()

    def _write(self):
        with self._lock:
            try:
                self.rec["written_at"] = time.time()
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.rec, f, indent=1)
                os.replace(tmp, self.path)
                self._last_write = self.rec["written_at"]
            except Exception:   # noqa: BLE001
                pass

    def output(self, frames_done=None, frames_total=None, phase=None):
        """The step printed something. Frame counts only ever move forward (workers can report out of
        order), and the file is rewritten at most every EVERY seconds from here."""
        now = time.time()
        with self._lock:
            r = self.rec
            r["last_output_at"] = now
            if frames_done is not None:
                if r["first_frame_at"] is None:
                    r["first_frame_at"] = now
                r["frames_done"] = max(frames_done, r["frames_done"] or 0)
            if frames_total:
                r["frames_total"] = frames_total
            if phase:
                r["phase"] = phase
            due = now - self._last_write >= EVERY
        if due:
            self._write()

    def facts(self, **kw):
        """What the renderer said about HOW it is working: drawing with the graphics chip or in software,
        how many workers, the per-stage timing at the end. Only changed values cause a write."""
        kw = {k: v for k, v in kw.items() if v not in (None, "")}
        with self._lock:
            f = self.rec.setdefault("facts", {})
            changed = any(f.get(k) != v for k, v in kw.items())
            f.update(kw)
        if changed:
            self._write()

    def stalled(self, seconds):
        with self._lock:
            self.rec["stall_seconds"] = int(seconds)
        self._write()

    def finish(self, result):
        """result: "ok", "failed (exit N)", or "stopped" (interrupted before it could end)."""
        self._done.set()
        with self._lock:
            self.rec["finished_at"] = time.time()
            self.rec["result"] = result
        self._write()


def recent(n=8, log_dir=None):
    """The newest n records, newest first. Unreadable files are skipped, never fatal."""
    out = []
    for f in sorted(glob.glob(os.path.join(log_dir or LOG_DIR, "*.json")), reverse=True)[:n]:
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except Exception:   # noqa: BLE001
            continue
    return out


def _dur(seconds):
    s = int(max(0, seconds or 0))
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


def _clock(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "?"


def _end(r, now):
    """The last moment this step was known to be alive."""
    return r.get("finished_at") or r.get("written_at") or r.get("started_at") or now


def speed(r):
    """Frames per second while frames were being drawn, or None. Measured from the first frame, so the
    browser's start-up time does not make a healthy render look slow."""
    done, t0, t1 = r.get("frames_done"), r.get("first_frame_at"), r.get("last_output_at")
    if done and t0 and t1 and t1 - t0 >= 5:
        return done / (t1 - t0)
    return None


def verdict(r, now=None):
    """One plain-words state: finished / failed / stopped / still running / never finished (+ froze)."""
    now = now or time.time()
    res = r.get("result") or "running"
    if res == "ok":
        return "finished"
    if res.startswith("failed"):
        return res
    if res == "stopped":
        return "stopped before it finished"
    if now - (r.get("written_at") or 0) <= ALIVE:
        return "still running right now"
    return "never finished (it was stopped from outside, or the computer slept or restarted)"


def describe(r, now=None):
    """One markdown bullet for a record."""
    now = now or time.time()
    start, end = r.get("started_at"), _end(r, now)
    bits = [f"**{r.get('step', 'step')}**"]
    if r.get("target"):
        bits.append(f"`{r['target']}`")
    bits.append(f"started {_clock(start)}")
    bits.append(f"ran {_dur(end - (start or end))}")
    done, total = r.get("frames_done"), r.get("frames_total")
    if done is not None and total:
        bits.append(f"frame {done:,} of {total:,}")
    elif total:
        bits.append(f"0 of {total:,} frames")
    v = speed(r)
    if v:
        bits.append(f"{v:.2f} frames/s")
        if total and done is not None and done < total:
            bits.append(f"at that speed the whole thing takes about {_dur(total / v)}")
    f = r.get("facts") or {}
    if f.get("gpu") == "software":
        bits.append("drawing in SOFTWARE (no graphics chip in use, the slowest way to render)")
    elif f.get("gpu"):
        bits.append(f"{f['gpu']} drawing")
    if f.get("workers"):
        bits.append(f"{f['workers']} worker{'s' if str(f['workers']) != '1' else ''}")
    line = "- " + " · ".join(bits) + f" → **{verdict(r, now)}**"
    if f.get("stages"):
        line += f" (stages: {f['stages']})"
    last_out = r.get("last_output_at")
    if r.get("result") != "ok" and last_out and end - last_out >= FROZE:
        line += (f". The renderer had printed nothing for {_dur(end - last_out)} by then, so it FROZE"
                 f" (last progress at {_clock(last_out)}), it was not just slow")
    elif (r.get("result") != "ok" and r.get("reports_progress", True) and not last_out
          and end - (start or end) >= FROZE):
        line += ". It never printed any progress at all, so it never really started"
    if r.get("stall_seconds"):
        line += f". The stall watcher fired after {_dur(r['stall_seconds'])} of silence"
    return line


def overlaps(records, now=None):
    """Pairs of steps that were alive at the same time. Each render already uses every core, so two at
    once is the single easiest way to turn minutes into hours."""
    now = now or time.time()
    spans = [(r.get("started_at") or 0, _end(r, now), r) for r in records]
    pairs = []
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            a0, a1, ra = spans[i]
            b0, b1, rb = spans[j]
            if a0 < b1 - 5 and b0 < a1 - 5:          # 5s slack: a hand-off from one step to the next is not overlap
                pairs.append((ra, rb))
    return pairs


def summarize(records, now=None):
    """Markdown lines for the report. Empty list when there is nothing to say."""
    now = now or time.time()
    if not records:
        return []
    lines = [describe(r, now) for r in records]
    for ra, rb in overlaps(records, now):
        lines.append(f"- ⚠ **Two ran at the same time:** the {ra.get('step')} started {_clock(ra.get('started_at'))} "
                     f"and the {rb.get('step')} started {_clock(rb.get('started_at'))} overlapped. Each one uses "
                     f"every core, so together both crawl. Renders run one at a time.")
    return lines


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:   # noqa: BLE001
            pass
    out = summarize(recent())
    print("\n".join(out) if out else "No slow steps recorded on this machine yet.")
