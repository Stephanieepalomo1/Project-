"""npx_run.py — build a subprocess argv that actually runs `npx` cross-platform.

On Windows, `npx` (like `npm`/`yarn`) is a batch script (`npx.cmd`), not a real .exe. Windows'
CreateProcess (what Python's subprocess uses without shell=True) can only launch real executables
directly — it cannot execute a .cmd/.bat file even when given its exact path with extension, so
`subprocess.run(["npx", ...])` fails with `FileNotFoundError: [WinError 2]` on every Windows machine,
while working fine on macOS/Linux (where `npx` is a real executable or a shebang script the OS can
exec directly). Routing through `cmd /c` lets Windows' own shell resolve and run the batch file
correctly; on Mac/Linux this wrapping is unnecessary, so leave the argv untouched there.
"""
import os
import platform
import sys


def hf_version():
    """The ONE HyperFrames pin, from product.json ("hyperframes"). Every render/check/bootstrap call reads
    it here, and check-ship refuses a bundle whose docs or scripts mention any other version, so a bump
    is one edit plus a doc sweep the gate verifies, never a hunt for stale copies.

    Fallbacks, in order: the shipped copy of product.json at product/templates/product.engine.json (an
    updater from v1.0.64 or earlier writes back a stale product.json and drops new settings; the template
    rides in every patch on an unprotected path), then the literal below, which check-ship §25 holds equal
    to the pin."""
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("product.json", os.path.join("product", "templates", "product.engine.json")):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                v = str(json.load(f).get("hyperframes", "")).strip()
            if v:
                return v
        except Exception:
            pass
    return "0.8.43"


def hf_check_timeout_ms():
    """Settle budget for `hyperframes check`. Its 3000 ms default was measured on Apple Silicon; an Intel
    Mac or a budget PC can miss it and fail a composition that is fine, and the render gate REFUSES to
    render on a failed check. One number, used by every caller, overridable for a tester whose machine
    needs more (REELS_ENGINE_HF_CHECK_TIMEOUT_MS)."""
    v = os.environ.get("REELS_ENGINE_HF_CHECK_TIMEOUT_MS", "").strip()
    if v.isdigit():
        return int(v)
    fast = (sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"))
    return 3000 if fast else 10000


def hf_check_argv(version, comp_dir, strict=False, timeout_ms=None, contrast=True):
    """The ONE argv for `hyperframes check`. Flag ORDER is load-bearing: on 0.7.68 (the earlier pin)
    `--frame-check` takes an optional value and its parser swallows whatever token follows it, so
    `--frame-check --timeout=3000` fails with "Invalid --frame-check" (a real regression: 1.0.65 shipped that
    order and every gated render would have refused; newer CLIs happen to accept it, which is how it hid).
    Keep `--timeout=` right after the directory and `--frame-check` LAST, on every version.
    contrast=False adds --no-contrast, for a composition whose visual content is NOT authored here
    (a background plate that reproduces the creator's own website verbatim). Her site's styling is
    hers to set; WCAG on it is not this gate's call, and restyling it to pass would defeat the point
    of using the real page. Every composition whose text IS authored here keeps the pass ON.

    product/tests/test_hf_check_argv.py runs this argv through the real CLI."""
    if timeout_ms is None:
        timeout_ms = hf_check_timeout_ms()
    args = ["check", comp_dir, f"--timeout={int(timeout_ms)}"]
    if strict:
        args.append("--strict")
    if not contrast:
        args.append("--no-contrast")
    args += ["--at-transitions", "--frame-check"]   # --frame-check LAST, always (see above)
    return npx_argv(f"hyperframes@{version}", *args)


def npx_argv(*args):
    """Return the argv list that actually invokes `npx <args>` on this OS."""
    if os.name == "nt":
        return ["cmd", "/c", "npx", *args]
    return ["npx", *args]


# Said by every caller that finds Node missing, so the wording is the same wherever it surfaces.
NO_NODE = ("Node is not installed on this computer, or this terminal was opened before it was installed "
           "(a new install stays invisible until the terminal is closed and opened again). HyperFrames runs "
           "on Node's `npx` command. Close the terminal and open a new one, then run this again; if it is "
           "still missing, run ./check-setup.sh, which prints the install command for this machine.")


def npx_path():
    """Where `npx` is on this machine, or None when Node is missing.

    Ask BEFORE running anything through npx_argv. On Windows that argv starts with `cmd`, which always
    exists, so a missing npx never raises: cmd prints "'npx' is not recognized" and exits 1, and a caller
    reading that exit code blames the composition. On a Mac a missing npx raises FileNotFoundError instead.
    `cmd /c npx` runs npx.cmd, so that is the name looked for on Windows."""
    import shutil
    return shutil.which("npx.cmd" if os.name == "nt" else "npx")
