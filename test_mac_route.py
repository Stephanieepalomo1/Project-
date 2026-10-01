#!/usr/bin/env python3
"""Guard: an Apple-chip Mac on a macOS older than Homebrew supports gets a setup that works.

Reported on launch day (2026-09-30): an Apple-chip buyer on macOS 13 (Ventura) ran the Homebrew installer
the setup handed her and it "stays there" at "Installing Command Line Tools for Xcode-14.3 / Finding
available software". Homebrew's floor is macOS 15 now (MACOS_OLDEST_SUPPORTED="15.0"), it ships ready-made
arm64 packages for 15 and newer only, and past that line every `brew install` would compile for hours.
Three things broke on those Macs, and each is pinned here:

  1. ROUTE. scripts/_mac-arch.sh mac_install_route sends an arm64 Mac below MAC_BREW_OLDEST down the
     no-Homebrew route (`direct`), keeps 15+ on `brew`, and leaves Intel and Rosetta exactly as before.
     check-setup.sh then prints only no-Homebrew lines on that Mac.
  2. INSTALLER. scripts/intel-mac-install.sh runs on that Mac, fetches Apple-chip ffmpeg/ffprobe (not
     Intel ones), and still refuses on an Apple-chip Mac Homebrew does support.
  3. NODE + PyAV. Node 24 needs macOS 13.5, so below it Node 22 is installed (on Intel too). PyAV's arm64
     wheels need macOS 14, so the transcriber install forces a wheel (`--only-binary av`) on a Mac instead
     of letting the resolver pick a source build that cannot compile there.

Run: python3 product/tests/test_mac_route.py
"""
import json, os, stat, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


# The Node release index, newest first, the way nodejs.org lists it: a Current release that is not LTS, the
# newest LTS (24, which needs macOS 13.5), then the 22 line.
NODE_RELEASES = [
    {"version": "v25.1.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": False},
    {"version": "v24.21.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Krypton"},
    {"version": "v22.23.3", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Jod"},
    {"version": "v22.22.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Jod"},
    {"version": "v20.19.5", "files": ["osx-x64-pkg"], "lts": "Iron"},
]


def fake_mac(tmp, machine="arm64", hw_arm64="1", macos="13.4"):
    """A copy of the route scripts on a simulated Mac. uname/sysctl/sw_vers say what we tell them, `file`
    reports whatever arch the downloaded zip says, and curl serves the indexes and small fake downloads,
    recording every URL. Returns (engine dir, env, record dir)."""
    eng, home, fake, rec, idx = (os.path.join(tmp, d) for d in ("eng", "home", "fakebin", "rec", "idx"))
    for d in (os.path.join(eng, "scripts"), home, fake, rec, idx, os.path.join(tmp, "t")):
        os.makedirs(d, exist_ok=True)
    for name in ("intel-mac-install.sh", "_mac-arch.sh"):
        with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as src, \
             open(os.path.join(eng, "scripts", name), "w", encoding="utf-8") as dst:
            dst.write(src.read())
    arch_word = "arm64" if machine == "arm64" else "x86_64"
    for tool in ("ffmpeg", "ffprobe"):
        # the "download": a stand-in binary that answers -version, tagged with the arch it was built for
        with zipfile.ZipFile(os.path.join(idx, f"{tool}.zip"), "w") as z:
            z.writestr(tool, f"#!/bin/sh\n# ARCH=ARM64BUILD\necho '{tool} version 9.0.2 Copyright (c) the FFmpeg developers'\n")
        with zipfile.ZipFile(os.path.join(idx, f"{tool}-intel.zip"), "w") as z:
            z.writestr(tool, f"#!/bin/sh\n# ARCH=X86BUILD\necho '{tool} version 8.0 Copyright (c) the FFmpeg developers'\n")
        with open(os.path.join(idx, f"{tool}.json"), "w", encoding="utf-8") as f:
            f.write('{"download":{"zip":{"url":"https:\\/\\/evermeet.cx\\/ffmpeg\\/%s-8.0.zip"}}}' % tool)
    with open(os.path.join(idx, "index.json"), "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in NODE_RELEASES) + "\n]\n")
    write_exec(os.path.join(fake, "uname"), f"#!/bin/sh\ncase \"$1\" in -m) echo {machine};; *) echo Darwin;; esac\n")
    write_exec(os.path.join(fake, "sysctl"), "#!/bin/sh\ncase \"$2\" in "
               f"hw.optional.arm64) [ '{hw_arm64}' = 1 ] && echo 1 || exit 1;; machdep.cpu.brand_string) echo 'Test CPU';; "
               "hw.physicalcpu) echo 8;; hw.logicalcpu) echo 8;; *) exit 1;; esac\n")
    write_exec(os.path.join(fake, "sw_vers"), f"#!/bin/sh\necho {macos}\n")
    # `file` reads the marker the fake zip wrote, so a wrong-arch download is caught like the real thing
    write_exec(os.path.join(fake, "file"), """#!/bin/sh
b=0; [ "$1" = -b ] && b=1 && shift
if grep -q ARM64BUILD "$1"; then a='Mach-O 64-bit executable arm64'; else a='Mach-O 64-bit executable x86_64'; fi
[ $b = 1 ] && echo "$a" || echo "$1: $a"
""")
    write_exec(os.path.join(fake, "xattr"), "#!/bin/sh\nexit 0\n")
    write_exec(os.path.join(fake, "open"), f"#!/bin/sh\necho \"$*\" >> '{rec}/OPENED'\n")
    write_exec(os.path.join(fake, "python3"), f"#!/bin/sh\necho \"$*\" >> '{rec}/POKED'\nexit 1\n")
    write_exec(os.path.join(fake, "curl"), f"""#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift ;; -m) shift ;; -*) ;; *) url="$1" ;; esac; shift; done
if [ -n "$out" ]; then
  echo "$url" >> '{rec}/DOWNLOADS'
  case "$url" in
    https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip) cp '{idx}/ffmpeg.zip' "$out" ;;
    https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip) cp '{idx}/ffprobe.zip' "$out" ;;
    *evermeet.cx/ffmpeg/ffmpeg-*.zip) cp '{idx}/ffmpeg-intel.zip' "$out" ;;
    *evermeet.cx/ffmpeg/ffprobe-*.zip) cp '{idx}/ffprobe-intel.zip' "$out" ;;
    *.pkg) echo pkg > "$out" ;;
    *) exit 22 ;;
  esac
  exit 0
fi
case "$url" in
  */info/ffmpeg/release) cat '{idx}/ffmpeg.json' ;;
  */info/ffprobe/release) cat '{idx}/ffprobe.json' ;;
  */dist/index.json) cat '{idx}/index.json' ;;
  *) exit 6 ;;
esac
""")
    for tool in ("sh", "bash", "dirname", "basename", "mktemp", "date", "sed", "tr", "grep", "cut", "head", "mkdir",
                 "rm", "cat", "chmod", "mv", "cp", "unzip", "wc", "printf", "id"):
        for d in ("/bin", "/usr/bin"):
            if os.path.exists(os.path.join(d, tool)):
                os.symlink(os.path.join(d, tool), os.path.join(fake, tool))
                break
    env = {"PATH": fake, "HOME": home, "TMPDIR": os.path.join(tmp, "t"), "LANG": "C"}
    return eng, env, rec


def sh(script, env, cwd):
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=env)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def ask(fn, **mac):
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, **mac)
        return sh(f". scripts/_mac-arch.sh; {fn}", env, eng)[1]


def main():
    print("1. which route each Mac gets")
    cases = [
        (dict(machine="arm64", macos="13.4"), "direct", "Apple chip, macOS 13.4 (the launch-day buyer)"),
        (dict(machine="arm64", macos="14.7.1"), "direct", "Apple chip, macOS 14"),
        (dict(machine="arm64", macos="15.0"), "brew", "Apple chip, macOS 15.0"),
        (dict(machine="arm64", macos="26.6.2"), "brew", "Apple chip, macOS 26"),
        (dict(machine="x86_64", hw_arm64="0", macos="15.7"), "direct", "true Intel Mac on 15"),
        (dict(machine="x86_64", hw_arm64="1", macos="13.4"), "rosetta", "Apple chip in a Rosetta terminal"),
        (dict(machine="arm64", macos=""), "brew", "unreadable macOS version never forces the slow route"),
    ]
    for mac, want, label in cases:
        got = ask("mac_install_route", **mac)
        check(f"{label} -> {want}", got == want, got)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, machine="arm64", macos="26.6.2")
        env["MAC_DIRECT_ROUTE"] = "1"
        got = sh(". scripts/_mac-arch.sh; mac_install_route", env, eng)[1]
        check("MAC_DIRECT_ROUTE=1 forces direct on a current Apple-chip Mac", got == "direct", got)

    print("2. which Node line each macOS gets")
    for macos, want in (("11.7.10", "22"), ("13.4", "22"), ("13.5", "lts"), ("13.7.8", "lts"), ("26.6.2", "lts")):
        got = ask("mac_node_line", machine="arm64", macos=macos)
        check(f"macOS {macos} -> {want}", got == want, got)

    print("3. the installer on an Apple-chip Mac below Homebrew's floor")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("ffmpeg + ffprobe install", rc == 0, f"rc={rc} {out} {err}")
        check("...from the Apple-chip builds, not evermeet's Intel ones", _lines(os.path.join(rec, "DOWNLOADS")) == [
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip",
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip"],
            _lines(os.path.join(rec, "DOWNLOADS")))
        landed = [os.path.join(env["HOME"], ".local", "bin", t) for t in ("ffmpeg", "ffprobe")]
        check("...and both run from ~/.local/bin", all(os.access(p, os.X_OK) for p in landed))
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        pkg = os.path.join(env["HOME"], "Downloads", "node-v22.23.3.pkg")
        check("node below 13.5 is the newest 22, not the newest LTS (24 will not start there)",
              rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-1:] == ["https://nodejs.org/dist/v22.23.3/node-v22.23.3.pkg"],
              f"rc={rc} {_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")
        check("...saved to Downloads and opened", os.path.exists(pkg) and _lines(os.path.join(rec, "OPENED")) == [pkg],
              _lines(os.path.join(rec, "OPENED")))
        check("Apple's python3 placeholder never ran", not os.path.exists(os.path.join(rec, "POKED")),
              _lines(os.path.join(rec, "POKED")))
        try:
            with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError) as e:
            log = e
        check("the step log records arm64 and the node step", isinstance(log, dict) and log.get("arch_class") == "arm64"
              and [(s["tool"], s["exit"]) for s in log["steps"]] == [("node", 0)], log)

    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="14.7.1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        check("macOS 14 gets the newest LTS", rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-1:] ==
              ["https://nodejs.org/dist/v24.21.0/node-v24.21.0.pkg"], f"{_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")

    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="15.1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("still refuses on an Apple-chip Mac Homebrew supports", rc == 2 and not _lines(os.path.join(rec, "DOWNLOADS")),
              f"rc={rc} {err}")

    print("4. Intel is unchanged, except Node on old macOS")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg && bash scripts/intel-mac-install.sh node", env, eng)
        got = _lines(os.path.join(rec, "DOWNLOADS"))
        check("Intel ffmpeg still comes from evermeet", rc == 0 and got[:2] == [
            "https://evermeet.cx/ffmpeg/ffmpeg-8.0.zip", "https://evermeet.cx/ffmpeg/ffprobe-8.0.zip"], f"rc={rc} {got} {err}")
        check("Intel on 13.4 also gets Node 22", got[-1:] == ["https://nodejs.org/dist/v22.23.3/node-v22.23.3.pkg"], got)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        # an Apple-chip zip handed to an Intel Mac must be refused, not installed
        with open(os.path.join(tmp, "fakebin", "curl"), encoding="utf-8") as f:
            body = f.read().replace("ffmpeg-intel.zip", "ffmpeg.zip")
        write_exec(os.path.join(tmp, "fakebin", "curl"), body)
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("a wrong-chip download is refused", rc != 0 and "not an x86_64 binary" in err, f"rc={rc} {err}")

    print("5. the checklist and the setup skill tell that Mac the truth")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, machine="arm64", macos="13.4")
        cs = open(os.path.join(ROOT, "check-setup.sh"), encoding="utf-8").read()
        # install_cmd, extracted and run against the simulated Mac, the same function check-setup.sh uses
        start = cs.index("install_cmd() {")
        fn = cs[start:cs.index("\n}\n", start) + 3]
        script = (". scripts/_mac-arch.sh; MACCLASS=$(mac_arch_class); MACROUTE=$(mac_install_route); OS=mac; "
                  "winget_line(){ echo winget; }\n" + fn + "\nfor t in ffmpeg uv node python3 pillow; do install_cmd $t; done")
        rc, out, err = sh(script, env, eng)
        check("no brew line for any tool", rc == 0 and "brew install" not in out and out.count("\n") == 4, f"{out} {err}")
        check("ffmpeg's line is the no-Homebrew installer", "intel-mac-install.sh ffmpeg" in out, out)
    check("check-setup routes on the install route, not the chip", '"$MACROUTE" = direct' in cs and "mac_install_route" in cs)
    sk = open(os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md"), encoding="utf-8").read()
    check("set-me-up asks for the route before handing over Homebrew", "mac_install_route" in sk and "`direct`" in sk)
    d = sk[sk.index("`direct` → an Apple-chip Mac"):]
    d = d[:d.index("- **`rosetta`")] if "- **`rosetta`" in d else d
    check("...and offers updating macOS as an OPTIONAL first choice, with the keep-going route beside it",
          "Offer her the choice FIRST" in d and "Software Update" in d and "Option 2, keep" in d
          and "Never push the update" in d and "intel-mac-install.sh all" in d)
    hook = open(os.path.join(ROOT, ".claude", "hooks", "machine-fingerprint.sh"), encoding="utf-8").read()
    check("the session hook warns Claude on that Mac", "mac_install_route" in hook)

    print("6. the transcriber never builds PyAV from source on a Mac")
    wt = open(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh"), encoding="utf-8").read()
    check("--only-binary av is set on Darwin", 'AV_WHEEL="--only-binary av"' in wt and '= "Darwin" ] && AV_WHEEL' in wt)
    installs = [ln.strip() for ln in wt.splitlines()
                if "uv pip install" in ln and not ln.strip().startswith("#") and ("whisperx" in ln or "faster-whisper" in ln)
                and "torch" not in ln]
    cpu = [ln for ln in installs if "$AV_WHEEL" not in ln]
    # the one install without it is the CUDA (NVIDIA, so Windows) branch
    check("every Mac-reachable whisper install carries it", len(installs) >= 3 and len(cpu) == 1, installs)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails)); sys.exit(1)
    print("all good: an Apple-chip Mac below Homebrew's floor sets up without Homebrew, and nothing else moved")


if __name__ == "__main__":
    main()
