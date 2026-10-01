# Motion craft: texture, restraint, and motion that reads as made

**Read this before planning graphics (step 3a), before building them (step 3b), and before writing an AI-b-roll
style block.** The creator is the feeling-informer: she says a beat should feel like paper, less digital, like
an old home video. This note is how that feeling turns into something a build can actually do. Studio's craft
floor keeps type, layout and color right; this keeps materials and motion right.

It is craft, not dressing. The look comes from her style pack; never retrofit a pack
from here. Reach for this note whenever you ideate beats, design a new graphic, treat footage, or generate AI
b-roll.

None of what follows is one big effect. Each dial is small and restrained, and the made-by-someone feel comes
from several of them stacked on top of clean design.

## Always on, everywhere

These four are part of the strong default: apply them everywhere, without being asked.

**Pull every effect back.** Restraint is the actual skill, and chromatic aberration shows it best: a hair of
RGB split sells a real lens, a heavy split looks amateur. Intensity climbs a ladder: lightest across a whole
composition, medium on a screen treatment, heaviest on archival or homogenized footage. The working rule: when
an effect first looks exciting, take about 40% back off it. That rule covers every effect in this note.

**No pure white.** Every room has a color temperature and paper takes it on, so tint a background a few percent
warm or cool. It matters twice: a texture laid over `#fff` is invisible, so pure white also quietly cancels the
texture dial below. The starter look's sky `#ddf4ff` already passes; keep anything new passing too.

**Lead the eye.** Give every busy composition a soft vignette, dialed subtle, so attention settles on the focal
point: radial darkening, or an edge blur sitting behind a feathered inverted radial mask.

**Draw icons and cutout props as SOLID FILL, with no stroked outline.** Whenever one is on screen: a
paper-cutout shape IS the cut paper, so the fill geometry makes its edge and a hard offset shadow makes its
depth, never a drawn border. No `stroke` around a filled icon, glyph, arrow or prop. Interior detail (a gear
hub, a half disc, the rim of a bell) is cut as one more solid fill in the second color, and the rim appears out
of the geometry. Things that genuinely are lines rather than outlined fills are exempt: wires, sound arcs,
brush strokes, tripod legs, register marks.

## Dial up when a beat should feel tactile, documentary, collage or archival

The heavier moves. They switch on when a beat wants to feel one of those ways.

**One texture.** A single texture per composition carries most of it. Halftone grunge turns a shape into a
newspaper cutout, paper fibre turns a panel into card, a light leak adds organic discoloration. A 50%-gray
texture composites with `mix-blend-mode: overlay`; a black-backed light leak wants `screen` or `plus-lighter`.
[texturelabs.org](https://texturelabs.org) is free, high resolution and safe for commercial use. Scale an
oversized texture down and let it interact with the tinted background instead of sitting on top of it.

**Printed edges.** A perfect edge looks computed. Rough up hairlines, rules and shape borders just enough to
read printed rather than plotted: SVG `feTurbulence` plus `feDisplacementMap` at a low scale of 2 to 3, or a
pre-textured PNG. Stop at printed, well short of wobbly; roughened too far, the element stops reading at all.

**Motion on twos.** Perfectly smooth interpolation reads sterile. Hand-drawn animation was drawn on every
second frame, and that slight choppiness is what reads as handmade. So quantize the graphic MOTION: 12 fps
(on twos), or 8 fps (on threes) for a more collaged beat. The part itself still RENDERS at base fps; the
stepping comes from GSAP `SteppedEase` or `"steps(n)"`, or from a progress quantiser on the timeline. Never lower the
render fps itself: the lock in `graphics-part-by-part.md` stands. Twos suit collage, paper and cutout motion.
Keep the talking head and any slow camera drift smooth.

**A screen is an object.** A raw screenshot or screen recording never goes on the frame untreated. Give it thin
horizontal scanlines (a repeating-linear-gradient at low opacity and softly feathered, roughly 8 px pitch at
1080p, duplicated at 90° when a laptop pixel-grid feel suits), medium chromatic aberration, a vignette, and a
subtle refresh flicker: an exposure ripple around 24 Hz at 2 to 5%, made from a precomputed per-frame array or
from layered sines. NEVER `Math.random`: the flicker has to stay deterministic and seek-safe. Then let a slow
camera drift across it while the line is spoken. That move lets the viewer discover the thing alongside the
narration, rather than being handed a slide.

## Outside and generated footage

This applies to every piece of outside footage and every generated clip, without exception.

**One finishing chain per job.** Archival, scraped, phone, stock and AI clips never match one another, and
cutting raw between two mismatched sources pulls the viewer right out of the story. So everything from outside
goes through a single finishing treatment, shared across the job: film grain over the top, the 24 Hz flicker,
chromatic aberration from the heavy end of the ladder, a hint of pixelation or CRT, and a consistent edge blur
(a feathered inverted radial mask). It can be as blunt as forced black and white plus heavy grain; what matters
is that the clips match, not which effects made them match. In practice that is a single ffmpeg chain run over
every external and generated clip, for example `rgbashift` at 1 px plus `vignette` plus
`noise=alls=8:allf=t+u`, with the values tuned per job. **For AI-generated b-roll this is the single biggest
lever: grain, a touch of aberration and a vignette kill the synthetic sheen immediately.**

**AI-b-roll style blocks.** Write the material into the prompt itself, so what comes back looks analog instead
of synthetic: handmade, tactile paper, halftone print texture, film grain, a little lens imperfection. Concept
words only, no CSS and no unit jargon. Then finish the clip through the job's shared chain so the whole set
matches.

## The last look

- Every effect sits at roughly half of whatever first looked exciting.
- Nothing in the frame is pure `#fff`.
- Eye guidance is present: a vignette or a masked blur.
- Any tactile composition carries at least one blended texture.
- Motion check: does smooth tweening actually serve this beat, or should it be stepping on twos?
- Screens are treated and drifting; every external or AI clip went through the job's shared chain.
