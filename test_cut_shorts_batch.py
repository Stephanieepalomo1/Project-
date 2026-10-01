#!/usr/bin/env python3
"""pull-reels' cut-shorts.py: one bad clip never costs the others their turn, a null hook means no hook, and
the splice runs under the bash a shell would find.

  batch    only a failed splice, caption or reframe step was treated as this clip's failure. An ffprobe error,
           or a clip the plan left without segments or a name, stopped the whole batch with a traceback.
  hook     "hook_text": null reached the command line as the word "None" and was drawn as the hook card.
  bash     a bare "bash" on Windows is looked up in System32 first, which is WSL's, not Git Bash.

The steps that shell out (splice, reframe, captions, export copy) are stood in for, so this runs in a second
and records exactly what each clip would have run.

Run: python3 product/tests/test_cut_shorts_batch.py
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


spec = importlib.util.spec_from_file_location(
    "cut_shorts_under_test", os.path.join(ROOT, ".claude", "skills", "pull-reels", "scripts", "cut-shorts.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def main():
    tmp = tempfile.mkdtemp(prefix="cut-shorts-batch-")
    real_tmp = tempfile.tempdir
    tempfile.tempdir = os.path.join(tmp, "scratch")
    os.makedirs(tempfile.tempdir)
    try:
        parent = os.path.join(tmp, "parent")
        os.makedirs(os.path.join(parent, "transcript"))
        with open(os.path.join(parent, "src.mp4"), "wb") as fh:
            fh.write(b"not really a video")
        with open(os.path.join(parent, "transcript", "words.json"), "w", encoding="utf-8") as fh:
            json.dump({"words": []}, fh)
        seg = [{"start": 0.0, "end": 1.5}]
        plan = {"source": "src.mp4", "clips": [
            {"name": "no-segments"},
            {"segments": seg},                                                     # no name at all
            {"name": "probe-fails", "segments": seg, "hook_text": "a real hook"},
            {"name": "null-hook", "segments": seg, "hook_text": None},
            {"name": "with-hook", "segments": seg, "hook_text": "said out loud", "hook_end": 2.5},
        ]}
        with open(os.path.join(parent, "clips-plan.json"), "w", encoding="utf-8") as fh:
            json.dump(plan, fh)

        ran = []
        def fake_run(cmd, env=None):
            ran.append([str(c) for c in cmd])
            return 0
        def fake_vertical(job, name, framing="fill"):
            if name == "probe-fails":
                raise subprocess.CalledProcessError(1, ["ffprobe", str(job)])
        real = (mc._run, mc._vertical, mc._export_copy)
        mc._run, mc._vertical, mc._export_copy = fake_run, fake_vertical, (lambda d, n: None)
        argv = sys.argv
        sys.argv = ["cut-shorts.py", parent, "--build"]
        out, err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                mc.main()
        except SystemExit as e:
            code = e.code
        finally:
            sys.argv = argv
            mc._run, mc._vertical, mc._export_copy = real

        said = out.getvalue()
        check("the run ends as a failure naming every failed clip",
              isinstance(code, str) and all(n in code for n in ("no-segments", "#2", "probe-fails"))
              and "null-hook" not in code and "with-hook" not in code, code)
        check("a clip without segments is reported, not a traceback", "no-segments: could not set up its folder" in said, said)
        check("a clip without a name is reported", "clip #2: the plan gives it no name" in said, said)
        check("an ffprobe error fails that clip only", "probe-fails: CalledProcessError" in said, said)
        check("the clips after the failures were still built", "✓ null-hook" in said and "✓ with-hook" in said, said)
        caps = {c[2].rsplit(os.sep, 1)[-1]: c for c in ran if c[1].endswith(os.path.join("clean-captions", "build.py"))}
        null = caps.get("null-hook")
        check("a null hook_text reaches the caption build as no hook, not the word None",
              null is not None and null[null.index("--hook-text") + 1] == "", null)
        hooked = caps.get("with-hook")
        check("a real hook and its end time still pass through",
              hooked is not None and hooked[hooked.index("--hook-text") + 1] == "said out loud"
              and hooked[hooked.index("--hook-end") + 1] == "2.5", hooked)
        splices = [c for c in ran if c[1].endswith("stitch-cut.sh")]
        want = shutil.which("bash") or "bash"
        check("the splice runs under the bash a shell would find", splices and all(c[0] == want for c in splices),
              [c[0] for c in splices])
    finally:
        tempfile.tempdir = real_tmp
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_cut_shorts_batch: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_cut_shorts_batch: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
