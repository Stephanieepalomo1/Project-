# Short-form layout sheet (9:16 reels)

What changes when the job is short-form, at **Graphics (step 3)** and **Captions (step 5)**, and nothing
else. The pipeline itself is the straight line in [CLAUDE.md](../CLAUDE.md): intake → rough cut → graphics →
second pass → captions → background music (optional) → export.

- **Frame:** 9:16 vertical, always **1080 × 1920**.
- **Destinations:** Instagram Reels, TikTok and YouTube Shorts, all three from one edit.
- **Length:** the tightest cut that delivers, with a target of ~1–2 min. The `rough-cut` skill already aims
  there (its "max value per second" filter governs). If the value fits in 40 s, ship 40 s. Never pad graphics
  or captions to stretch a reel to a length.

---

## The safe box: the one layout rule never to break

**The top 270 px and bottom 300 px hold NO key visuals, only background or filler.** The face, the captions
and every key visual (graphics, hero text, numbers, logos, hook cards) must sit **inside the safe box: y
`270 → 1620`**. The two bands may carry background, grid, glow or B-roll bleed, nothing the viewer actually
needs, because that is where the platform UI and the device chrome land.

| Band | Size | What covers it |
|------|------|----------------|
| **Top** | **270 px** | status bar / platform header (Reels reserves 14% = 269 px) |
| **Bottom** | **300 px** | caption UI, username, audio tag, CTA, progress bar |

**Where the numbers come from:** `product/safe_zones.py`, and the engine CHECKS every placement against them
at build time, so never hardcode a band again. The top is the strictest band across Reels, TikTok and Shorts
(Meta reserves the **top 14% and bottom 20%** of a Reel). The bottom 300 is the creator's explicit, locked
call, looser than every platform's published band; `violations(..., platform="reels")` still checks one
platform's real band when asked. Per platform: Reels `269 → 1536` · TikTok `260 → 1440` · Shorts
`180 → 1540`. TikTok's bottom is heavier still, and it adds a right-hand action rail: keep wide elements left
of x`900`, where TikTok and Reels stack their action buttons.

**Why it is measured rather than eyeballed:** a UI collision is invisible in the render, invisible in
QuickTime and invisible in the preview. You only see it in the app, on a phone, after posting. An earlier top
band of 200 (with the same 300 at the bottom) shipped a reel whose persistent label sat under Instagram's
Reels header.

Inside the box: the hook card sits inside its top, graphics sit in the open space around her, and the face is
framed inside it.

---

## Which look: the register points the way

A short-form talking head takes one of two looks. Both start from the same rough cut, full frame, and differ only
at Graphics (3). The register usually settles it: **teaching** carries graphics through the reel, **Clean
Captions** is the trimmed-back look, right for a confessional reel. If it doesn't, ask one line: *"graphics
through it, or just the hook card?"*

---

## Teaching, graphics through it (graphics-plan's `reel-teaching`)

**Her full-frame talking head, with graphics in the open space around her.** Most teaching beats get a graphic:
the hook, every concrete claim, every stat, the payoff.

- **Reframe to 9:16:** crop to 1080×1920 if the footage isn't already.
- **Graphics (step 3):** plan first with `graphics-plan` (which lines get a graphic, which stay plain), then build
  in HyperFrames in her style pack. Every graphic sits in the open space around her, read from this job's
  `subject-zones.json` (`workflows/subject-zones.py`), never over her face, and inside the safe box above.
  A beat that wants motion with no real footage behind it can be generated as a clip first, then composited like
  any part.
- **Captions (step 5):** through her style pack or CapCut's Auto Captions, in their own band. Feed the derived
  transcript; never re-transcribe.

---

## Clean Captions, the trimmed-back look (graphics-plan's `reel-clean`)

**Her full-frame talking head, raw, with one front hook card as the only graphic.** The lightest finish.
A single reel captions through her style pack or CapCut's Auto Captions (`product/FLOW.md`). The burn-in
builder in [`presets/clean-captions-style.md`](../presets/clean-captions-style.md) is what `pull-reels` uses when
asked for `--captions clean`, and what it falls back to for any clip whose style-pack captions (its default,
in beta) cannot finish.

- **Reframe to 9:16:** crop to 1080×1920 if the footage isn't already.
- **Graphics (step 3):** a single **hook card** (locked look: `presets/clean-captions-style.md`) pinned to
  the **top** of the safe zone. It appears at the start and **disappears once the hook lands** (~first
  2–4 s); after that the footage plays raw. No other graphics, no B-roll, no lower-thirds.
- **Captions (step 5):** **low, under the face**, inside the caption-safe band (locked look:
  `presets/clean-captions-style.md`). Feed the derived transcript; never re-transcribe.

---

## No sales asks

CTA decisions live in your content system, and the script carries any ask. This edit adds none: captions and
end screens stay clean (see CLAUDE.md Rules).
