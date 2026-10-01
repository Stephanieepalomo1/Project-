<!-- Starter values, not anyone's brand yet. To make them yours, fill out brand-kit.md and say
     "use my brand kit", or change the values in this file by hand. -->

# Starter type

Your reels take their fonts and colors from the style pack you pick. This page holds one thing: the headline
font the engine falls back to before a pack is chosen. If you swap in your own headline font, "use my brand kit"
writes it here, and your choice is kept through every update.

## Type: Inter, the fallback headline font

The files are `assets/fonts/Inter-{Black,Bold,Regular}.otf`. A HyperFrames project needs its own copies in its
`assets/fonts/` folder, loaded with `@font-face`, because a render can only use a font it has on disk.

- **Headline:** Inter Black, mixed case, a little tight (`letter-spacing: -2px`, `line-height` near `1.0`).
- **Label:** Inter Bold.
- **Subtitle:** Inter Regular, sentence case.

Before sizing a long headline, measure its widest word (PIL's `ImageFont.getlength`) against the frame instead of
guessing.
