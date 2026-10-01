#!/usr/bin/env python3
"""The Intel-Mac wheel pins in the engine's requirements survive future edits.

Two pin sets are guarded: the VectCutAPI cryptography cap, and the background-music (MusicGen)
stack. Both exist for the same reason -- a package dropped its macOS x86_64 wheel and an Intel Mac
then has nothing to install -- and both are gated so no other machine is held back.

WHY: cryptography 49.0.0 dropped its macOS universal2 wheel and now publishes arm64 ONLY. It arrives
transitively (oss2 -> aliyun-python-sdk-core -> cryptography), so on an Intel Mac pip silently falls
through to the sdist and tries to COMPILE it, which needs Rust and Apple's Command Line Tools. Neither
is on the machine this route exists for, so `setup-editor-engine.sh` died partway through installing
the engine's tools -- reported live by a buyer on an Intel Mac.

This guard pins the two properties that make the fix correct, so a later tidy-up of requirements.txt
cannot quietly reopen it: the cap is there for Intel, and it does NOT hold Apple Silicon or Windows
back to an old cryptography. Offline -- it reads the file and evaluates markers, it installs nothing.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REQ = os.path.join(ROOT, "product", "engine", "VectCutAPI", "requirements.txt")
fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


# packaging is not in a stock python3; pip vendors it. Either is fine, and if neither is importable
# the textual checks below still run rather than the guard reporting a pass it did not make.
Requirement = None
for _mod in ("packaging.requirements", "pip._vendor.packaging.requirements"):
    try:
        Requirement = __import__(_mod, fromlist=["Requirement"]).Requirement
        break
    except Exception:
        continue

lines = [ln.split("#", 1)[0].strip() for ln in open(REQ, encoding="utf-8")]
lines = [ln for ln in lines if ln]
crypto = [ln for ln in lines if ln.lower().startswith("cryptography")]

check("requirements.txt carries a cryptography line", len(crypto) == 1)
if not crypto:
    print("\nFAILED: the Intel cryptography pin is gone from requirements.txt")
    sys.exit(1)

line = crypto[0]
check("...capped below 49, the first arm64-only release", "<49" in line.replace(" ", ""))
check("...and gated by a marker, so it is not a global downgrade", ";" in line)

if Requirement is None:
    print("\nSKIPPED the marker checks: no packaging module importable (textual checks passed)")
    sys.exit(1 if fails else 0)

req = Requirement(line)
check("the pin parses as a real requirement", req.name == "cryptography")
if req.marker is None:
    # An ungated pin would hold Apple Silicon and Windows back to an old cryptography too. Report
    # that plainly rather than raising on the marker checks below, which have nothing to evaluate.
    check("the pin is gated by a marker", False)
    print("\nFAILED: " + "; ".join(fails))
    sys.exit(1)

INTEL = {"sys_platform": "darwin", "platform_machine": "x86_64"}
SILICON = {"sys_platform": "darwin", "platform_machine": "arm64"}
WINDOWS = {"sys_platform": "win32", "platform_machine": "AMD64"}

check("an Intel Mac gets the pin", req.marker.evaluate(INTEL))
check("...so does a Rosetta'd terminal, which hits the same wall", req.marker.evaluate(INTEL))
check("Apple Silicon is left on current cryptography", not req.marker.evaluate(SILICON))
check("Windows is left on current cryptography", not req.marker.evaluate(WINDOWS))

check("48.x, the last universal2 wheel, is allowed", req.specifier.contains("48.0.1"))
check("49.0.0, the first arm64-only wheel, is excluded", not req.specifier.contains("49.0.0"))
check("and every later arm64-only release is too", not req.specifier.contains("50.0.1"))

# --- the background-music (MusicGen) stack -------------------------------------------------------
# torch's last macOS x86_64 wheel is 2.2.2. transformers 5.x demands torch>=2.5, and numpy 2.x
# breaks torch 2.2.2's ABI. Unpinned, an Intel buyer asking for a music bed gets a FAILED INSTALL,
# not a slow one. Each cap is marker-gated so every other machine stays on current releases.
MUSIC_REQ = os.path.join(ROOT, "product", "requirements-music.txt")

print("\n  -- background music (MusicGen) --")
check("product/requirements-music.txt exists", os.path.exists(MUSIC_REQ))
if os.path.exists(MUSIC_REQ):
    mlines = [ln.split("#", 1)[0].strip() for ln in open(MUSIC_REQ, encoding="utf-8")]
    mlines = [ln for ln in mlines if ln]

    # Each package needs BOTH an Intel-capped line and an uncapped line for everyone else, so the
    # cap can never become a global downgrade and the feature can never vanish off Apple Silicon.
    for name, cap, allowed, blocked in (
        ("torch", "<2.3", "2.2.2", "2.3.0"),
        ("transformers", "<5", "4.56.0", "5.0.0"),
        ("numpy", "<2", "1.26.4", "2.0.0"),
    ):
        pins = [Requirement(ln) for ln in mlines if Requirement(ln).name == name]
        intel = [r for r in pins if r.marker is not None and r.marker.evaluate(INTEL)]
        silicon = [r for r in pins if r.marker is not None and r.marker.evaluate(SILICON)]

        check(f"{name}: an Intel Mac gets exactly one pin", len(intel) == 1)
        check(f"{name}: Apple Silicon gets exactly one, separate line", len(silicon) == 1)
        if len(intel) == 1:
            spec = str(intel[0].specifier).replace(" ", "")
            check(f"{name}: the Intel line is capped {cap}", cap.replace(" ", "") in spec)
            check(f"{name}: {allowed} (has an Intel wheel) is allowed",
                  intel[0].specifier.contains(allowed))
            check(f"{name}: {blocked} (no Intel wheel) is excluded",
                  not intel[0].specifier.contains(blocked))
        if len(silicon) == 1:
            check(f"{name}: Apple Silicon is NOT capped",
                  not str(silicon[0].specifier).strip())

print("\n" + ("FAILED: " + "; ".join(fails) if fails
             else "the Intel wheel pins hold, and only on the machines that need them"))
sys.exit(1 if fails else 0)
