# Third-Party Notices

The Reels Editing Engine is built and sold by Homewell LLC. It bundles or builds upon the open-source
components listed below, each used under its own license and credited here as those licenses require.
Nothing in this file limits your rights under those upstream licenses. Components that install on your
own machine at runtime (and are therefore not redistributed inside this package) are listed at the end
for completeness.

---

## Bundled components

### HyperFrames
- Source: https://github.com/heygen-com/hyperframes
- Copyright (c) HeyGen and the HyperFrames contributors.
- License: Apache License 2.0 (a copy is included in this package at `product/engine/VectCutAPI/LICENSE`,
  and the full text is available at https://www.apache.org/licenses/LICENSE-2.0).
- Used by the HyperFrames-family skills under `.claude/skills/` (hyperframes, hyperframes-core,
  hyperframes-animation, hyperframes-cli, hyperframes-creative, hyperframes-keyframes,
  hyperframes-registry, hyperframes-audio, media-use, faceless-explainer, general-video,
  product-launch-video, motion-graphics, slideshow, and related video-authoring skills).

### VectCutAPI and pyJianYingDraft
- Sources: VectCutAPI, https://github.com/sun-guannan/VectCutAPI (copyright its contributors), which
  includes pyJianYingDraft, https://github.com/GuanYixuan/pyJianYingDraft (copyright its contributors).
- Bundled at `product/engine/VectCutAPI/` (its own `LICENSE` file is retained there).
- License: Apache License 2.0.
- Modified by Homewell LLC. Each changed file carries a notice at the top saying so; files added by
  Homewell LLC (the setup and launcher scripts, `requirements-lock.txt`) are not part of the original.
- Used as the CapCut / JianYing draft-building engine. This package is not affiliated with or endorsed
  by the VectCutAPI or pyJianYingDraft authors, or by CapCut.

### talking-head-recut (adapted from vtake-skills)
- Source: https://github.com/notedit/vtake-skills
- Copyright (c) 2026 leeoxiang.
- License: MIT (full text below; the original notice is retained at
  `.claude/skills/talking-head-recut/NOTICE.md`).

### GSAP, the GreenSock Animation Platform (v3.15.0)
- Source: https://gsap.com
- Copyright (c) GreenSock, Inc.
- License: GreenSock standard "no charge" license (https://gsap.com/standard-license), free for use in
  commercial products. The license header is retained inside the bundled `gsap.min.js`.

### Bundled sound effects (fallback set, in `.claude/skills/media-use/audio/assets/sfx/`)
- Source: Pixabay (https://pixabay.com). Each file is credited in that folder's `CREDITS.md`.
- License: Pixabay Content License (https://pixabay.com/service/license-summary/), free for commercial
  use with no attribution required. Provided only as a fallback; you may replace them with your own.

### Bundled public-domain sound effects (`product/creative-vault/sfx/cc0/`)
- Sources: uisfx (https://uisfx.com), synthesized by its author; and "100 CC0 SFX #2" by rubberduck
  (https://opengameart.org/content/100-cc0-sfx-2).
- License: Creative Commons CC0 1.0 Universal (public domain), free for any use including commercial,
  with no attribution required. Each file's origin is listed in `product/creative-vault/sfx/cc0/SOURCES.md`.

### Bundled fonts (open-license, in `assets/fonts/`)
- **SIL Open Font License 1.1** (full text in `assets/fonts/OFL.txt`, plus `OFL-Inter.txt`,
  `OFL-SpaceGrotesk.txt` and `OFL-Caveat.txt`): Inter, Space Grotesk, Caveat, DM Sans, Instrument Serif, Julius Sans One,
  Noto Sans Adlam, Pinyon Script, Playfair Display, Poppins, Shrikhand. Each font keeps its own
  copyright notice inside the font file.
- **Coolvetica** — copyright Typodermic Fonts Inc., free for commercial use under Typodermic's own
  license (https://typodermicfonts.com). That license ships with the font, at `assets/fonts/COOLVETICA-LICENSE.txt`.
- The style packs' premium display faces (Prosecco, Soup Du Jour, Ugly Dave, Bloop, ZY Modern, Advercase,
  Geomanist, Opera Cake) are NOT bundled and never redistributed by this package; CapCut Pro resolves them by
  name from its own font library on your machine.

### Face detection model (`assets/models/face_detection_yunet_2023mar.onnx`)
- **YuNet**, from the OpenCV Model Zoo (https://github.com/opencv/opencv_zoo). Copyright (c) 2020 Shiqi Yu.
  MIT License; the full text ships beside the model, at `assets/models/YUNET-LICENSE.txt`.

---

## Installed at runtime on your own machine (NOT redistributed in this package)

These tools are downloaded and installed onto your own computer the first time you run the engine. They
are not included in this package and remain under their own licenses:

- HyperFrames CLI (`npx hyperframes`) — Apache-2.0
- WhisperX and its models (faster-whisper, wav2vec2) — BSD / MIT
- FFmpeg — LGPL / GPL, as installed on your machine: through Homebrew on a Mac, through winget on Windows, and
  as the static evermeet.cx build on an Intel Mac
- MusicGen (`facebook/musicgen-small`), downloaded only if you use generated background music: the model is
  licensed **CC BY-NC 4.0, non-commercial**. Tracks it makes are for trying a vibe; for anything you post or
  sell, use music you have the rights to.
- Python packages installed during setup ("set me up"; `check-setup.sh` only reports what is missing), for
  example Pillow — their own licenses

---

## MIT License (for talking-head-recut / vtake-skills)

```
MIT License

Copyright (c) 2026 leeoxiang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The Apache License 2.0 that governs HyperFrames and VectCutAPI is included in full in this package at
`product/engine/VectCutAPI/LICENSE`.
