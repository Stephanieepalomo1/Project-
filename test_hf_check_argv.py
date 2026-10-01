#!/usr/bin/env python3
"""Guard: the `hyperframes check` argv the gate builds is one the pinned CLI actually accepts.

The regression this prevents: 1.0.65 built `... --at-transitions --frame-check --timeout=3000`. On 0.7.68
(the pin at the time) `--frame-check` takes an optional value and swallows the token after it, so every gated
render was refused with "Invalid --frame-check" before it ever looked at the composition. Newer CLIs happen
to accept that order, which is exactly why only a live run against the CURRENT pin proves anything. Reading the code cannot
catch that; only running the real CLI can. This test builds a minimal composition and runs the exact argv
through `npx hyperframes@<pin> check`. It passes when the CLI parses the flags (whatever it then thinks of
the composition) and fails on any "Invalid --..." or "Unknown flag" response. Skips when npx is absent.

Run: python3 product/tests/test_hf_check_argv.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from npx_run import hf_check_argv, hf_check_timeout_ms   # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def pin():
    try:
        v = json.load(open(os.path.join(os.path.dirname(HERE), "..", "product.json"), encoding="utf-8")).get("hyperframes")
        if v:
            return str(v)
    except Exception:
        pass
    import reel_render
    return reel_render.HF_VERSION


MINI_HTML = """<!doctype html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden;background:transparent}
#root{position:absolute;inset:0}.t{position:absolute;top:400px;left:120px;font:700 80px/1 sans-serif;color:#fff}</style></head>
<body><div id="root" data-composition-id="mini" data-start="0" data-duration="1.00" data-width="1080" data-height="1920">
<div class="clip" id="clip-a" data-start="0" data-duration="1.00" data-track-index="1"><div class="t" id="t0">hello</div></div>
</div></body></html>
"""
MINI_JSON = {"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
             "media": {"autoProxy": True}}


def main():
    print("hyperframes check argv\n")
    v = pin()
    argv = hf_check_argv(v, "/tmp/x", strict=False)
    tail = argv[argv.index("check"):]
    check("--timeout comes right after the composition dir", tail[2].startswith("--timeout="), str(tail))
    check("--frame-check is the last token (nothing for it to swallow)", tail[-1] == "--frame-check", str(tail))
    s = hf_check_argv(v, "/tmp/x", strict=True)
    st = s[s.index("check"):]
    check("--strict never follows --frame-check", st.index("--strict") < st.index("--frame-check"), str(st))
    check("timeout is a positive integer", hf_check_timeout_ms() >= 500)

    if not shutil.which("npx"):
        print("  SKIP  live CLI parse (npx not on PATH)")
    else:
        d = tempfile.mkdtemp(prefix="hf-argv-")
        try:
            open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(MINI_HTML)
            json.dump(MINI_JSON, open(os.path.join(d, "hyperframes.json"), "w", encoding="utf-8"))
            for strict in (False, True):
                cmd = hf_check_argv(v, d, strict=strict)
                cmd.insert(1, "--yes") if cmd[0] == "npx" else None
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                    out = re.sub(r"\x1b\[[0-9;]*m", "", (p.stdout or "") + (p.stderr or ""))
                except subprocess.TimeoutExpired:
                    out = "TIMEOUT"
                bad = re.search(r"Invalid --[a-z-]+|Unknown flag|Unknown option|unknown option", out)
                check(f"hyperframes@{v} accepts the argv (strict={strict})", bad is None and out != "TIMEOUT",
                      (bad.group(0) if bad else out[-300:]))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
