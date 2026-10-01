# The style plan — LOCKED spec + paste-ready functional widget

> The one canonical definition of the rough-cut review step, the **style plan** (formerly "cut sheet" —
> renamed for creators 2026-08-01). Rule 2 in `CLAUDE.md` points here. **Preferred path: generate it with
> `product/build-style-plan.py <job-dir>`** — the generator bakes in the canvas-blank fail-safe (below)
> and never mis-replaces a token, so hand-assembly can't drift. The skeleton below is the reference the
> generator emits; build from it by hand only if the generator can't run. Only the cut (from
> `cuts.json`) changes per job. Format-agnostic: the SAME style plan is used for **Yap, Voiceover, and
> Animation** — there is no per-format variant.

## The contract (do not drift)

**COST POLICY — widget FIRST, lean table on every RE-CUT (2026-08-25).** The interactive `show_widget`
is ~25K output tokens per render (~15x a plain markdown table), and re-rendering it on every re-cut is
the single biggest avoidable cost in the cut stage. So: the **first** time a cut is reviewed, deliver the
full interactive widget (the delightful reveal). For **every re-cut after that**, deliver the **lean
markdown table** (below) instead — same information, ~1.5K tokens, the user replies with edits by line
number. This keeps the beautiful first look and kills the repeat-render tax that quietly drains a creator's
monthly usage. (Applies identically to the shipped engine — leaner shipped = more reels/month.)

Every rough-cut review is **two things, in this order**, in the chat — **on EVERY format (Yap,
Voiceover, Animation), no exceptions:**

1. A **markdown video link in the chat text** — path to the rough-cut MP4 **relative to the working
   directory (the engine root)**, e.g. `▶ [<job>.mp4](projects/<job>/outputs/<job>.mp4) — 1:18`. This
   opens the side-panel player **so she can WATCH the rough cut before approving**. It goes DIRECTLY
   ABOVE the review, always. **NEVER** a `SendUserFile`, inline-render, or attach card, and **NEVER `open`
   the MP4 with a shell command** (that launches QuickTime or another external app). The markdown link is
   the only way you surface the cut; it plays in the side panel, in place.
   > 🔴 **Generate the link, don't hand-type it** — `python3 product/style_plan_link.py <job>` prints the
   > exact markdown, computed from the engine root and **existence-checked**, and REFUSES a missing or
   > wrongly-prefixed path. `build-style-plan.py` prints it for you too. Validate any link you already
   > wrote with `python3 product/style_plan_link.py --check "<href>"`.
   > **Do NOT prefix the engine folder name** (`ai-edit-engine/…`): the session's working directory IS
   > the engine folder, so a link resolves from there; prefixing it doubles the path to
   > `…/ai-edit-engine/ai-edit-engine/projects/…` and the preview fails with "Couldn't load this preview
   > / file may have been deleted or moved." The href is just `projects/<job>/outputs/<job>.mp4`.
2. The cut review itself:
   - **First review of a given reel → the interactive `show_widget`** (the style plan) built from the skeleton below.
   - **Every re-cut review after that → the LEAN MARKDOWN TABLE** (format below), NOT the widget.
   - **🔴 EXACTLY ONE style plan on screen per review.** Call `show_widget` a SINGLE time for a first review — never twice, never a re-issue "to be safe," and never the widget PLUS the plain-text/table version in the same turn (they are an either/or: widget when `show_widget` works, plain-text only as the no-widget fallback). Two style plans for one review is the bug to prevent.

**Lean re-cut table** — plain markdown the app renders for ~1/15th the tokens; the user replies with edits
by line number (no interactive controls):

```
| # | line | dur |
|---|------|-----|
| 1 | so if you wanna know how i edit my yaps… | 8.1s |
| 2 | and no, i did not hire an editor… | 3.9s |
| … | … | … |

**total: 1:25 · reply with cuts/notes by line number**
```

An italic section label (Hook / Setup / …) may head a group of rows. Keep the same line numbering the
widget would use so her edits map straight back to `cuts.json`.

**Layout is fixed — one row per kept line:**
- **LEFT** — two icon buttons in a HORIZONTAL row: attach (`ti-paperclip`) + notes (`ti-message`).
- **MIDDLE** — line number + the transcript line (+ inline fields when opened). An optional subtle,
  sentence-case section tag above a group of rows (Hook / Setup / …) is allowed.
- **RIGHT** — duration + trash toggle (`ti-trash`), in a horizontal row.
- **Header** — a counter (`kept · trashed · notes`) on the left, and a live **length meter** on the right
  that turns **green in the 0:45–1:30 sweet spot** (amber above 1:30, neutral below 0:45).
- **Footer** — `Send my edits ↗` (primary) + `Reset`, in a horizontal row.

**Icons:** Tabler **outline** webfont only — `ti-paperclip`, `ti-message`, `ti-trash`,
`ti-arrow-up-right`, `ti-refresh` (already loaded in `show_widget`; do NOT hand-draw SVG icon paths, the
platform blocks them, and NEVER use emoji). Buttons always in HORIZONTAL rows, never stacked.

## 🔴 EVERY BUTTON MUST FUNCTION — the locked functional rules

The style plan is an INTERACTIVE tool, not a picture. All three buttons must do something visible.

- **🔴 BIND EVERY HANDLER IN JS VIA `addEventListener` — NEVER inline `onclick="…"` HTML attributes.**
  The `show_widget` sandbox blocks / does not resolve inline event-handler attributes (CSP + wrapped
  script scope), so any button wired with `onclick="fn()"` is **dead on arrival while JS-attached buttons
  work** — that is the exact bug that shipped 2026-08-05 (note/trash worked, Send/Reset were dead). All
  buttons — send, reset, attach, note, trash, copy — attach their handlers in the script with
  `el.addEventListener("click", fn)`. There is **no** `onclick=` attribute anywhere in the markup.
- **🔴 WRAP THE SCRIPT IN AN IIFE AND SCOPE EVERY QUERY TO ITS OWN ROOT.** The root `<div>` carries
  `data-sp-root` (plus an `sp-<job>` id for a11y); the script resolves its root via `document.currentScript`
  / first un-hydrated `[data-sp-root]` (see the CANVAS-BLANK FAIL-SAFE below — **not** `getElementById`,
  which collides on duplicate ids) and queries only `root.querySelector(...)` (via `data-*` hooks, not
  global ids). This keeps two style plans
  in one session from colliding on global `const`s (a redeclare = SyntaxError that kills the second
  widget) or duplicate element ids. No top-level `const`/`function` leaks to global scope.
- **🔴 SEND ALWAYS SURFACES THE EDITS — never trust `sendPrompt`'s return.** `sendPrompt` can SILENTLY
  no-op: it returns without throwing but nothing lands in the chat. So a guarded call that reveals the
  copy box only ON failure still dead-ends when the call "succeeds" but does nothing (regression
  2026-08-11). Therefore `sendEdits()` ALWAYS reveals the copy box pre-filled with the compiled message
  AND copies it to the clipboard (`document.execCommand('copy')`), whether or not `sendPrompt` reported
  success. Attempt `sendPrompt` (guarded by `typeof` + `try/catch`) as the fast path, but the visible,
  selectable copy-paste box is the guaranteed path that makes Send impossible to break.
- **NEVER use `prompt()`, `alert()`, or `confirm()`** for the note / attach buttons. The `show_widget`
  sandbox **blocks** them, so the button silently does nothing. The attach + note buttons MUST open an
  **inline field** (`<textarea>` / `<input>`) rendered inside the row that the user types into, with
  `oninput` writing straight to state.
- **Trash** toggles the row's kept/trashed state and restyles it (strike-through + dim).
- Typing in a field updates the header counts live **without** a full re-render (a full re-render on every
  keystroke steals focus). Toggling a field open/closed re-renders, then focuses the new field.
- **Send my edits** compiles trashed line numbers + notes + references into a plain message and calls
  `sendPrompt(...)` (guarded, per above). If nothing changed, it sends an "approved, move on" message.
- **Reset** clears all state, hides the fallback, and re-renders.

If you change the skeleton, keep every button functional — re-test that clicking attach/note reveals a
typable field, that Send fires (or falls back to the copy box), and that Send carries the typed text.

## 🔴 CANVAS-BLANK FAIL-SAFE — the widget must never render empty (root fix, locked 2026-09-04)

**Symptom (recurring):** the style plan "doesn't load in the canvas" — it renders as an empty shell,
usually the *newest* one on screen. **Root cause:** every render's script located its root with
`document.getElementById("sp-<job>")`, and `getElementById` returns the **first** match. When the same
job's style plan renders twice in a session (a re-render after a fix, or the canvas re-materializing the
earlier widget), the second script hydrates the *first* widget's DOM and leaves the newer one's rows
empty. All content was JS-built into an empty `[data-rows]`, so a mis-scope — or any script throw —
left a blank box. Reproduced deterministically: two same-id renders → instance #2 had 0 rows.

Two locked layers of defense, both baked into `build-style-plan.py`:

- **🔴 SELF-SCOPING — bind to THIS render's own root, never a global id.** The script resolves its root
  from `document.currentScript` (its immediately-preceding `[data-sp-root]` sibling); if that is
  unavailable it claims the **first un-hydrated** `[data-sp-root]` and marks it `data-sp-hydrated`. This
  is immune to duplicate ids AND a null `currentScript`, so two renders each bind to their own instance.
  **Never** reintroduce `getElementById` as the scoping mechanism.
- **🔴 STATIC FALLBACK — every line is a visible static row in the markup, and hydration is wrapped in
  try/catch.** The numbered cut + durations are present with zero JS; hydration replaces them with the
  interactive rows. If the script never runs or throws, the canvas still shows the full read-only cut
  plus a "reply by line number" notice. The review degrades to readable, never to blank.

Verify after any change to the widget: render it **twice in one page with the same id** and confirm BOTH
instances populate their rows (not just the first).

## Paste-ready skeleton (functional: JS-bound handlers, IIFE scope, sendPrompt fallback)

**Prefer the generator** (`python3 product/build-style-plan.py <job-dir> [--job NAME]`) — it fills all of
this in and cannot slip a token. If you hand-build, per render replace: (1) the `SEGS` array (one entry
per kept segment from `cuts.json`; `sec` = optional section tag, `s`/`e` = start/end seconds so the row
prints its own duration); (2) the **static fallback rows** inside `[data-rows]` (one `data-static-row`
per SEG — never ship an empty `[data-rows]`); (3) the root id `sp-JOB` on the `<div data-sp-root
id="sp-JOB">` — make it `sp-<job>`; and (4) **every** `JOB` token (the id plus BOTH `compile()`
strings — miss the lowercase "the JOB rough cut" and the Send message ships literal "JOB"). The script
scopes itself via `data-sp-root` + `currentScript`, so there is **no** `getElementById`, **no** global
id lookup, and **no** inline `onclick=` to break.

```html
<h2 class="sr-only">Interactive style plan: each kept line is removable, with inline note and reference fields and a live length meter.</h2>
<div data-sp-root id="sp-JOB" style="padding: 0.5rem 0 1.25rem;">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px;">
    <div style="display:flex; gap:16px; font-size:13px; color:var(--text-secondary);">
      <span><span data-kept style="color:var(--text-primary); font-weight:500;">0</span> kept</span>
      <span><span data-trashed style="color:var(--text-primary); font-weight:500;">0</span> trashed</span>
      <span><span data-notes style="color:var(--text-primary); font-weight:500;">0</span> notes</span>
    </div>
    <div style="display:flex; align-items:center; gap:10px;">
      <div style="width:150px; height:6px; border-radius:999px; background:var(--surface-1); overflow:hidden;">
        <div data-meter-fill style="height:100%; width:0%; background:var(--text-secondary); transition:width .2s, background .2s;"></div>
      </div>
      <span data-meter-label style="font-size:13px; font-weight:500; min-width:74px; text-align:right;">0:00</span>
    </div>
  </div>
  <div data-rows style="display:flex; flex-direction:column; gap:6px;">
    <!-- STATIC FALLBACK: build-style-plan.py emits one <div data-static-row> per SEG here (number +
         line + duration), so the cut is visible with zero JS. render() replaces these on hydration.
         If you hand-build, emit them; do NOT ship an empty [data-rows]. -->
  </div>
  <div style="display:flex; gap:10px; margin-top:16px; flex-wrap:wrap;">
    <button type="button" data-send>Send my edits <i class="ti ti-arrow-up-right" aria-hidden="true"></i></button>
    <button type="button" data-reset><i class="ti ti-refresh" aria-hidden="true"></i> Reset</button>
  </div>
  <div data-fallback style="display:none; margin-top:14px; padding:12px; border:0.5px solid var(--border-strong); border-radius:var(--radius); background:var(--surface-1);">
    <div data-fallback-note style="font-size:13px; color:var(--text-secondary); margin-bottom:8px;">Copy this and paste it into the chat.</div>
    <textarea data-fallback-text readonly rows="5" style="width:100%; font-size:13px; resize:vertical;"></textarea>
    <button type="button" data-copy style="margin-top:8px;">Copy to clipboard <i class="ti ti-copy" aria-hidden="true"></i></button>
  </div>
</div>
<script>(function(){
  // FAIL-SAFE SCOPING (see "CANVAS-BLANK FAIL-SAFE" above): bind to THIS render's own root, NEVER a
  // shared global id. Two renders of the same job share id="sp-JOB"; getElementById returns the FIRST,
  // so the newer widget renders blank. currentScript resolves our own sibling; else claim the first
  // un-hydrated root. Immune to duplicate ids AND a null currentScript.
  var me = document.currentScript;
  function pickRoot(){
    if (me && me.previousElementSibling && me.previousElementSibling.matches &&
        me.previousElementSibling.matches("[data-sp-root]")) return me.previousElementSibling;
    var all = document.querySelectorAll("[data-sp-root]");
    for (var i=0;i<all.length;i++){ if(!all[i].hasAttribute("data-sp-hydrated")) return all[i]; }
    return all.length ? all[all.length-1] : null;
  }
  var root = pickRoot();
  if (!root) return;
  root.setAttribute("data-sp-hydrated","1");
  try {
  const q = s => root.querySelector(s);
  const SEGS = [
    {n:1, sec:"Hook", t:"First kept line goes here.", s:11.3, e:19.5},
    {n:2, sec:"Hook", t:"Second kept line.", s:19.9, e:23.1},
  ];
  const state = {};
  SEGS.forEach(g => state[g.n] = {trashed:false, note:"", ref:"", noteOpen:false, refOpen:false});
  const fmt = sec => { const m=Math.floor(sec/60), s=Math.round(sec%60); return m+":"+String(s).padStart(2,"0"); };
  const hasMeta = st => (st.note && st.note.trim()) || (st.ref && st.ref.trim());
  function refreshCounts(){
    let kept=0, trashed=0, notes=0, dur=0;
    SEGS.forEach(g => { const st=state[g.n]; if(st.trashed) trashed++; else { kept++; dur+=(g.e-g.s); } if(hasMeta(st)) notes++; });
    q("[data-kept]").textContent = kept;
    q("[data-trashed]").textContent = trashed;
    q("[data-notes]").textContent = notes;
    q("[data-meter-label]").textContent = fmt(dur);
    const fill = q("[data-meter-fill]");
    fill.style.width = Math.min(100, dur/120*100) + "%";
    const good = dur>=45 && dur<=90;
    fill.style.background = good ? "var(--text-success)" : (dur>90 ? "var(--text-warning)" : "var(--text-secondary)");
    q("[data-meter-label]").style.color = good ? "var(--text-success)" : "var(--text-primary)";
  }
  function makeField(g, kind){
    const st = state[g.n];
    const wrap = document.createElement("div"); wrap.style.cssText = "margin-top:8px; display:flex; flex-direction:column; gap:4px;";
    const lbl = document.createElement("label"); lbl.textContent = kind === "note" ? "Note" : "Reference or link";
    lbl.style.cssText = "font-size:11px; color:var(--text-muted); letter-spacing:.03em;";
    const inp = document.createElement(kind === "note" ? "textarea" : "input");
    if(kind === "note"){ inp.rows = 2; inp.style.cssText = "width:100%; resize:vertical; font-size:13px; padding:6px 8px;"; }
    else { inp.type = "text"; inp.placeholder = "paste a link, timestamp, or file path"; inp.style.cssText = "width:100%; font-size:13px;"; }
    inp.value = kind === "note" ? st.note : st.ref;
    inp.oninput = e => { if(kind === "note") st.note = e.target.value; else st.ref = e.target.value; refreshCounts(); };
    wrap.appendChild(lbl); wrap.appendChild(inp); return { wrap, inp };
  }
  function render(){
    const rows = q("[data-rows]"); rows.innerHTML = ""; let lastSec = null; let focusTarget = null;
    SEGS.forEach(g => {
      const st = state[g.n];
      if(g.sec && g.sec !== lastSec){
        const h = document.createElement("div"); h.textContent = g.sec;
        h.style.cssText = "font-size:11px; letter-spacing:.04em; color:var(--text-muted); margin:8px 0 2px 2px;";
        rows.appendChild(h); lastSec = g.sec;
      }
      const row = document.createElement("div");
      row.style.cssText = "display:flex; align-items:flex-start; gap:12px; padding:10px 12px; border:0.5px solid var(--border); border-radius:var(--radius); background:var(--surface-2);" + (st.trashed ? "opacity:.5;" : "");
      const left = document.createElement("div"); left.style.cssText = "display:flex; gap:4px; flex:0 0 auto; padding-top:1px;";
      const attachBtn = document.createElement("button"); attachBtn.type = "button";
      attachBtn.innerHTML = '<i class="ti ti-paperclip" aria-hidden="true"></i>';
      attachBtn.setAttribute("aria-label","Add a reference to line "+g.n);
      attachBtn.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (((st.ref && st.ref.trim()) || st.refOpen) ? "border-color:var(--border-accent); color:var(--text-accent);" : "");
      attachBtn.addEventListener("click", () => { st.refOpen = !st.refOpen; if(st.refOpen) st._focus = "ref"; render(); });
      const noteBtn = document.createElement("button"); noteBtn.type = "button";
      noteBtn.innerHTML = '<i class="ti ti-message" aria-hidden="true"></i>';
      noteBtn.setAttribute("aria-label","Add a note to line "+g.n);
      noteBtn.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (((st.note && st.note.trim()) || st.noteOpen) ? "border-color:var(--border-accent); color:var(--text-accent);" : "");
      noteBtn.addEventListener("click", () => { st.noteOpen = !st.noteOpen; if(st.noteOpen) st._focus = "note"; render(); });
      left.appendChild(attachBtn); left.appendChild(noteBtn);
      const mid = document.createElement("div"); mid.style.cssText = "flex:1 1 auto; min-width:0;";
      const line = document.createElement("div");
      line.style.cssText = "font-size:14px; line-height:1.5;" + (st.trashed ? "text-decoration:line-through; color:var(--text-muted);" : "color:var(--text-primary);");
      const num = document.createElement("span"); num.textContent = g.n;
      num.style.cssText = "color:var(--text-muted); font-variant-numeric:tabular-nums; margin-right:8px;";
      line.appendChild(num); line.appendChild(document.createTextNode(g.t));
      mid.appendChild(line);
      if(st.refOpen){ const f = makeField(g, "ref"); mid.appendChild(f.wrap); if(st._focus === "ref") focusTarget = f.inp; }
      if(st.noteOpen){ const f = makeField(g, "note"); mid.appendChild(f.wrap); if(st._focus === "note") focusTarget = f.inp; }
      st._focus = null;
      const right = document.createElement("div"); right.style.cssText = "display:flex; align-items:center; gap:8px; flex:0 0 auto;";
      const dur = document.createElement("span"); dur.textContent = fmt(g.e-g.s);
      dur.style.cssText = "font-size:12px; color:var(--text-secondary); font-variant-numeric:tabular-nums; min-width:30px; text-align:right;";
      const trash = document.createElement("button"); trash.type = "button";
      trash.innerHTML = '<i class="ti ti-trash" aria-hidden="true"></i>';
      trash.setAttribute("aria-label", (st.trashed?"Restore":"Cut")+" line "+g.n);
      trash.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (st.trashed ? "border-color:var(--border-danger); color:var(--text-danger);" : "");
      trash.addEventListener("click", () => { st.trashed = !st.trashed; render(); refreshCounts(); });
      right.appendChild(dur); right.appendChild(trash);
      row.appendChild(left); row.appendChild(mid); row.appendChild(right); rows.appendChild(row);
    });
    if(focusTarget) focusTarget.focus();
  }
  function compile(){
    const trashed = SEGS.filter(g => state[g.n].trashed).map(g => g.n);
    const notes = SEGS.filter(g => state[g.n].note && state[g.n].note.trim()).map(g => 'line '+g.n+' ("'+g.t.slice(0,40)+'…"): '+state[g.n].note.trim());
    const refs  = SEGS.filter(g => state[g.n].ref && state[g.n].ref.trim()).map(g => 'line '+g.n+': '+state[g.n].ref.trim());
    if(trashed.length===0 && notes.length===0 && refs.length===0){
      return "The JOB rough cut looks good, no changes. Move on to the creative plan.";
    }
    let msg = "Here are my edits to the JOB rough cut:\n";
    if(trashed.length) msg += "\nCut these lines: "+trashed.join(", ")+".";
    if(notes.length) msg += "\nNotes:\n- "+notes.join("\n- ");
    if(refs.length) msg += "\nReferences:\n- "+refs.join("\n- ");
    msg += "\n\nRe-cut with these changes, then show me the updated cut.";
    return msg;
  }
  function deliver(msg){
    try { if (typeof sendPrompt === "function"){ sendPrompt(msg); return true; } } catch(e){}
    return false;
  }
  // FAIL-SAFE: Send ALWAYS surfaces the compiled edits in the copy box + copies them to the clipboard,
  // whether or not sendPrompt reports success. sendPrompt can silently no-op, so its return is NEVER
  // trusted as proof of delivery — the copy box is the guaranteed path, so Send can never do nothing.
  function sendEdits(){
    const msg = compile();
    const sent = deliver(msg);
    const fb = q("[data-fallback]"), ta = q("[data-fallback-text]"), note = q("[data-fallback-note]");
    ta.value = msg; fb.style.display = "block";
    if(note) note.textContent = sent
      ? "Sent to the chat. If it didn't appear there, copy this and paste it to me:"
      : "Copy this and paste it into the chat:";
    ta.focus(); ta.select();
    try { document.execCommand("copy"); } catch(e){}
  }
  function resetSheet(){ SEGS.forEach(g => { state[g.n]={trashed:false, note:"", ref:"", noteOpen:false, refOpen:false}; }); q("[data-fallback]").style.display = "none"; q("[data-fallback-text]").value = ""; render(); refreshCounts(); }
  q("[data-send]").addEventListener("click", sendEdits);
  q("[data-reset]").addEventListener("click", resetSheet);
  q("[data-copy]").addEventListener("click", () => { const ta = q("[data-fallback-text]"); ta.focus(); ta.select(); try { document.execCommand("copy"); } catch(e){} });
  render(); refreshCounts();
  } catch(err){
    // Hydration failed: keep the static rows (they already show every line + duration) so the canvas is
    // never blank, and add a short notice so the review still works by line number.
    root.setAttribute("data-sp-degraded","1");
    var n=document.createElement("div");
    n.style.cssText="margin-top:10px; font-size:12px; color:var(--text-secondary);";
    n.textContent="(Showing the read-only cut. Reply with any cuts or notes by line number.)";
    root.appendChild(n);
  }
})();</script>
```

## Wiring it to the re-cut

When she hits **Send my edits**, the returned message names the line numbers to cut. Two copies of the cut
exist, and each has one job:

- **`projects/<job>/transcript/cuts.json`** is the cut the last splice saved, and the one the style plan was
  built from, so her line N is its segment N (same order as `SEGS`). **Make her edits here**
  (delete/adjust).
- **`<temp dir>/reels-editing-engine/<job>/cuts.json`** (`<temp dir>` = Python's `tempfile.gettempdir()`) is
  the plan `stitch-cut.sh` actually stitches, and whatever it stitches it saves over the copy above. So **copy the
  edited file over it before splicing**, or the next splice stitches the old plan and saves it over her edits:

  ```bash
  python3 -c "import os,shutil,sys,tempfile; d=os.path.join(tempfile.gettempdir(),'reels-editing-engine',sys.argv[1]); os.makedirs(d,exist_ok=True); shutil.copy(os.path.join('projects',sys.argv[1],'transcript','cuts.json'),d)" <job>
  ```

Then re-run `stitch-cut.sh` and show the updated cut with a fresh style plan. (If the scratch folder has been
cleared, `stitch-cut.sh` stitches the saved copy by itself and says so.) Notes/references that aren't "cut this"
are creative direction — carry them into the plan.

> Internal data/filenames (`cuts.json`, `stitch-cut.sh`, the `rough-cut` skill) keep their names — the
> "style plan" rename is creator-facing wording only, not code churn.
