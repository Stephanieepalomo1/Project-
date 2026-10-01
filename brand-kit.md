# 🏡 Brand Kit — your Homebase, written down

<!-- GATE GUARD: the onboarding-complete check counts double-angle-bracket placeholder tokens in this file.
     Never write a literal double-angle-bracket placeholder in prose or instructions here. It belongs only
     on the real fields below, or a fully filled file will still read as "not set up." -->

This file is your **Brand Homebase** on paper: who your reels are for, how you sound, and the few defaults
that make an edit yours. Caption voice, on-thumbnail copy and the style of your graphics all read from
what you put here.

**You don't have to fill it in by hand.** Say **"build my homebase"** and Claude interviews you one
question at a time, writes your answers in here, and applies them. (Built a Homebase in another product
already? **"Sync my homebase"** pulls it in.) Would you rather type it? Replace every placeholder below
(each one sits between double angle brackets), then say **"use my brand kit"** and Claude writes the
values into the presets for you. **Part B** at the bottom is the exact list of what changes where, for
checking the work or doing it yourself.

Filling this in is strongly recommended, never required. While any placeholder is still here the editor
treats this as a fresh install and offers to walk you through setup, but it edits whenever you ask: a reel
builds fine without this file once you've picked a style pack, which sets your fonts and colors. Until it is
filled in your reels simply carry no personal voice, never someone else's handle, hook or colors, and no
placeholder text ever reaches the screen.

---

# Part A — your answers

It runs in the order the Homebase interview goes: who you help, how you sound, your look, then two small
extras.

## Who you are, and who you help (identity)

- **You and your brand:** `<<FILL_ME: your name — your brand (yourbrand.com)>>`
- **Who you help, and what they walk away with:** `<<FILL_ME: who you help + the outcome, in one sentence>>`
- **Where you post:**
  - Instagram: `<<FILL_ME: @yourhandle>>`
  - TikTok: `<<FILL_ME or "none">>`
  - YouTube Shorts: `<<FILL_ME: channel name or "not used">>`  ·  channel ID: `<<FILL_ME or n/a>>`

> _One line of guidance:_ this is who the videos are FOR and who's making them. Be specific, not broad.
> A few shapes to borrow: "people who keep killing their sourdough starter," "first-time owners of a
> reactive rescue dog," "freelancers who dread their own bookkeeping," "runners coming back from an
> injury." Any of those beats "busy people." The niche shapes every hook and caption you'll get back.

## How you sound (voice & tone)

Captions, hooks and every other line of on-screen copy get written to this, so it is worth the most care.
Tell it the way a friend would describe how you talk: the energy, the sentence length, whether you go
lowercase, how much slang. A few honest lines beat a page of adjectives.

```
<<FILL_ME: 2–3 lines describing how you talk. Give the vibe, sentence length, casing habits, humor, and
any values woven in. End with a gut-check you would use on a line. Three examples in three different
worlds, so you can see the shape and then write your own:
  · "Calm and exact, like a shop teacher who likes you. Short sentences. No hype words. Gut check: would
    I say this with my hands in the dough?"
  · "Fast, funny, a little chaotic. Lowercase, lots of fragments, one joke per post. Gut check: would
    this make my group chat laugh?"
  · "Warm and unhurried. Plain words, no jargon, never rushed. Gut check: would a nervous beginner feel
    calmer after reading this?"
Yours, in your own words.>>
```

## The rules your copy never breaks (hard rules)

> _One line of guidance:_ list the things Claude must NEVER do in your copy. Delete the samples that
> don't apply and add your own. These are enforced on every caption and hook.

- `<<FILL_ME: a punctuation or formatting rule. A good one to steal: "No em dashes anywhere. Use periods and short sentences." It is one of the clearest AI tells.>>`
- `<<FILL_ME: banned phrases and clichés you never want to see in your copy. Pick your own. Common ones people ban: "game-changer," "unlock," "level up," "crushing it," "literally obsessed.">>`
- `<<FILL_ME: a tone red line, the thing your copy must never do. Examples: "never imply the viewer is doing it wrong," "never fake urgency," "never promise a number I cannot back up.">>`

## The lines you actually say (voice DNA) — optional but powerful

> _One line of guidance:_ paste 3–6 of your own recurring phrases, sentence shapes, and sign-offs. The
> more real lines you give, the more the copy sounds like you and not a template.

- `<<FILL_ME: a signature sentence structure you use. Shapes other creators use: "you'd think X. it's actually Y." or "three things nobody tells you about X." or a question you answer in one word.>>`
- `<<FILL_ME: 2–3 phrases you actually say out loud. Things like "here's the part nobody mentions," "quick one," "okay so," "the honest answer is." Yours, not borrowed.>>`
- `<<FILL_ME: how you tend to close. Examples: "that's it, go try it." / "save this for the weekend." / "tell me if it works." / you just stop, no sign-off.>>`

## Your look: the style pack, plus two font lines

Your colors are never typed in anywhere. They come with the style pack you pick in the interview
(Editorial, Playful or Butter), and that one pick sets your whole look. The two lines below name the fonts
for the bundled graphics and caption looks.

- **Headline font** (titles and graphics): `<<FILL_ME: font name, or "Inter" to keep the bundled default>>`
  - _Guidance:_ bringing your own? Put its `.otf` or `.ttf` files in `assets/fonts/` (it needs **Black,
    Bold and Regular** weights) and write its name here. Leave it as **Inter** and there is nothing to
    install: Inter comes bundled with the engine.
- **Caption font** (burned-in captions): `<<FILL_ME: font name, or "Coolvetica" to keep the bundled default>>`
  - _Guidance:_ Coolvetica comes with the engine, in `assets/fonts/`, and it is the locked caption look.
    Name a different face only if you want your captions to have a different identity.

## Words the transcriber mishears (caption auto-corrections)

The transcriber (WhisperX) gets some names wrong, usually a product or brand name. Write each one as
`heard → correct` and the captions fix it for you, every time.

```
<<FILL_ME: one per line, e.g.
canva → Canva
yourbrandname → YourBrandName
>>
```

> ⚠️ **ONE WORD PER KEY.** The corrector looks at one transcribed word at a time, so a two-word key such
> as `"canva pro"` can never match: it arrives as two separate words. Fix a multi-word name by hand, or
> per job in `projects/<job>/corrections.local.json`.

## Hook defaults (the front card)

- **A hook you reuse on every reel:** `<<FILL_ME: a default on-screen hook, or "blank" to set it per video>>`
  - _Guidance:_ "blank" is a fine answer — most creators write the hook per video. A fixed default only
    helps if your reels share one recurring opener.
- **The word that ends the hook card:** `<<FILL_ME: the word that ends the hook card, or "blank" for first sentence>>`
  - _Guidance:_ leave "blank" to auto-end the card at the first sentence break. Override per job with
    `--hook-end` when a card should hold longer.

---

# Part B — what applying your kit updates

"Build my homebase" runs this list at the end of the interview, and **"use my brand kit"** runs it after
you have edited Part A yourself. It is the spec Claude follows, so read on only if you want to check the
work or do it by hand.

| From Part A | Lands in | What changes |
|---|---|---|
| Who you are, who you help, where you post, how you sound | `CLAUDE.md`, in its **Brand Kit** section | your name, niche, handles and voice/tone go there, and from then on captions and on-screen copy everywhere are written in that voice |
| Your look | the **style pack** you pick during setup (Editorial / Playful / Butter) | nothing to fill in: each pack carries its own signature colors and the graphics presets read from it, not from a hand-entered palette. Pick a pack and its look is applied for you. |
| Headline font, if you swapped it | `presets/type-and-look.md` | the `Inter-{Black,Bold,Regular}` filenames (and the "Inter" name) are swapped for your own font's files, and those have to be in `assets/fonts/`. Staying on Inter (bundled)? Nothing changes. |
| Words the transcriber mishears | `presets/caption-corrections.json` | each `heard → correct` pair is filed under `"auto"`, which fixes caption text quietly; a word that is also a real word goes under `"flag"` instead, which lists it on every run so you can look it over |
| Hook defaults | `presets/clean-captions/build.py` | the hook you reuse becomes `DEFAULT_HOOK_TEXT`, and the word that ends the card goes into the line that spots the end of the spoken hook |
| Your logos (no field above: just add the files) | `assets/logos/` | the logos or marks you'd like available on screen |

There is no face-reference folder to fill: this engine is short-form only, and a reel COVER is chosen from
your own footage by the `cover-thumbnail` skill, so it needs nothing collected in advance.

**How you'll know it took.** After applying, run one real clip through as a quick test. The titles should
be in your font, and your pack's accent color should show up on the emphasis word. `./check-setup.sh`
confirms the fonts are found.

---

# Part C — Reel style memory (Claude learns your pattern)

You do not fill this in. **Claude does, as you go.** This is how the editor gets more "you" with every reel
instead of starting from scratch each time.

Here is the whole idea, and it is the good part: your editable CapCut draft always comes back **fully
populated** — every caption, sticker, sound, and clip already placed. Your job is just to **nudge the layout
to perfection**: move a word up, resize a sticker, shift a beat, swap a sound. When you have it how you like
it, say the magic sentence:

> **"Learn my pattern for the next reel."**

Claude writes what you changed into the log below (in plain words), and **reads it before building your next
reel** — so next time those choices are already baked in. Each reel needs fewer tweaks than the last. The
more you use the flow, the more it edits like you would.

You can also just tell it a preference out loud anytime — "my captions sit a little higher," "I like the
punch-in zoom on the first line," "keep sound effects lighter" — and say "remember that." Same result.

### How it actually works now

Saying the sentence writes the preference **twice**: the bullet below, in plain language for you, and a
record the builders read on every build (`_local/learned.json`, via `product/learned.py`). The bullet is
what you read; the record is what makes the next reel come out different. Both, every time — a bullet on
its own is a note, not a setting.

Two things you can always do:

- **"/learn list"** — everything you have taught it, with the reel and date each one came from.
- **"/learn forget 3"** — drop one. Do this the moment a reel needs a correction that undoes something you
  taught; a stale preference is worse than none, because you cannot see it working.

Every build prints what it took from this list, so a reel is never quietly different for reasons you cannot
see.

**Some things are deliberately NOT learnable**, and the engine will say so and offer the nearest thing:

- **Teaching vs confessional, and how done you want it** — asked fresh each reel, because they are
  decisions about THAT video.
- **Your hook** — it is written against what the reel is doing, and it must never just repeat your spoken
  opener. A remembered hook is a wrong hook.
- **An exact position on screen** — where you are in frame is measured on YOUR footage every reel. A number
  that sat perfectly above your head in one video lands on your forehead in the next. So "I like my captions
  a little higher" is saved as *which open space to prefer*, and the number still comes from the footage in
  front of it.

### Learned preferences (Claude appends here — leave it empty to start)

```
(empty for now — this fills in as you say "learn my pattern for the next reel")
```

> _For Claude:_ **load the `learn` skill** — it owns this, and it is the only thing that keeps the promise
> above. Saving a preference means writing BOTH halves: `python3 product/learned.py add <field> <value>
> "<her words>"` (what the builders apply, validated and clamped) AND a short plain-language bullet here
> (what she reads). Run `python3 product/learned.py fields` for what is learnable. Scope a preference to the
> register or format it came from unless it is genuinely global. Never delete an earlier bullet; refine it by
> teaching the field again. And never tell her something was learned when only the bullet was written — that
> sentence was said once and was not true of a single build afterwards.
