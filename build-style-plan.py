#!/usr/bin/env python3
"""Canonical generator for the style-plan review widget (the rough-cut review surface).

Emits the HARDENED, self-scoping, fail-safe widget so it can never be hand-assembled wrong or render
blank in the canvas again. Two layers of defense are baked in and cannot be forgotten:

  1. SELF-SCOPING (root fix). Every render's script binds to ITS OWN root via `document.currentScript`
     (falling back to the first un-hydrated root), NEVER `getElementById`. Two renders of the same job
     share the same base id; `getElementById` returns the FIRST, which left the newer widget blank
     ("not loading in the canvas"). Self-scoping is immune to duplicate ids and a null currentScript.
  2. STATIC FALLBACK (degradation). Every line is emitted as a visible static row in the markup and the
     hydration body is wrapped in try/catch. If the script never runs or throws, the canvas still shows
     the full numbered cut + a "reply by line number" notice. The review is never a blank box.

Usage:
    python product/build-style-plan.py <job-dir> [--job NAME] [--out FILE]

<job-dir> holds transcript/cuts.json ({"segments":[{start,end,transcript,...}]}). Optional section tags:
transcript/style-plan-sections.json = {"1":"Hook","18":"Confession",...} (1-based line -> tag). Prints
the widget HTML to stdout, or to --out. Feed the result to show_widget on the FIRST review only; re-cuts
use the lean markdown table (see style-plan-widget.md cost policy).
"""
import json, sys, os, html, argparse

def fmt(s):
    m = int(s // 60); sc = round(s % 60)
    return f"{m}:{sc:02d}"

def build(job_dir, job=None):
    job = job or os.path.basename(os.path.normpath(job_dir))
    cuts = json.load(open(os.path.join(job_dir, "transcript", "cuts.json"), encoding="utf-8"))
    segs = cuts["segments"]
    sec_path = os.path.join(job_dir, "transcript", "style-plan-sections.json")
    sections = {int(k): v for k, v in json.load(open(sec_path, encoding="utf-8")).items()} if os.path.exists(sec_path) else {}

    segs_js, static_rows, last = [], [], None
    for i, s in enumerate(segs, 1):
        tag = sections.get(i)
        secf = json.dumps(tag) if (tag and tag != last) else '""'
        if tag and tag != last:
            static_rows.append(f'<div style="font-size:11px; letter-spacing:.04em; color:var(--text-muted); margin:8px 0 2px 2px;">{html.escape(tag)}</div>')
            last = tag
        t = json.dumps(s["transcript"]); dur = fmt(s["end"] - s["start"])
        segs_js.append(f'    {{n:{i}, sec:{secf}, t:{t}, s:{s["start"]:.3f}, e:{s["end"]:.3f}}},')
        static_rows.append(
            f'<div data-static-row style="display:flex; gap:12px; padding:10px 12px; border:0.5px solid var(--border); '
            f'border-radius:var(--radius); background:var(--surface-2); font-size:14px; line-height:1.5;">'
            f'<span style="color:var(--text-muted); font-variant-numeric:tabular-nums;">{i}</span>'
            f'<span style="flex:1 1 auto; color:var(--text-primary);">{html.escape(s["transcript"])}</span>'
            f'<span style="color:var(--text-secondary); font-variant-numeric:tabular-nums;">{dur}</span></div>')

    total = fmt(sum(s["end"] - s["start"] for s in segs))
    w = _TEMPLATE
    w = w.replace("__SEGS__", "\n".join(segs_js))
    w = w.replace("__STATIC__", "\n    ".join(static_rows))
    w = w.replace("__KEPT0__", str(len(segs)))
    w = w.replace("__METER0__", total)
    w = w.replace("JOB", job)               # id + both compile strings + comment, all at once
    assert "JOB" not in w, "leftover JOB token"
    return w

_TEMPLATE = r'''<h2 class="sr-only">Interactive style plan: each kept line is removable, with inline note and reference fields and a live length meter.</h2>
<div data-sp-root id="sp-JOB" style="padding: 0.5rem 0 1.25rem;">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px;">
    <div style="display:flex; gap:16px; font-size:13px; color:var(--text-secondary);">
      <span><span data-kept style="color:var(--text-primary); font-weight:500;">__KEPT0__</span> kept</span>
      <span><span data-trashed style="color:var(--text-primary); font-weight:500;">0</span> trashed</span>
      <span><span data-notes style="color:var(--text-primary); font-weight:500;">0</span> notes</span>
    </div>
    <div style="display:flex; align-items:center; gap:10px;">
      <div style="width:150px; height:6px; border-radius:999px; background:var(--surface-1); overflow:hidden;">
        <div data-meter-fill style="height:100%; width:0%; background:var(--text-secondary); transition:width .2s, background .2s;"></div>
      </div>
      <span data-meter-label style="font-size:13px; font-weight:500; min-width:74px; text-align:right;">__METER0__</span>
    </div>
  </div>
  <div data-rows style="display:flex; flex-direction:column; gap:6px;">
    __STATIC__
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
  // FAIL-SAFE SCOPING: bind to THIS render's own root, never a shared global id. Two renders of the same
  // job share id="sp-JOB"; getElementById returns the FIRST, so the newer widget stays blank ("not
  // loading in the canvas"). currentScript resolves our own sibling; else claim the first un-hydrated
  // root. Immune to duplicate ids AND a null currentScript.
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
__SEGS__
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
    const notes = SEGS.filter(g => state[g.n].note && state[g.n].note.trim()).map(g => 'line '+g.n+' ("'+g.t.slice(0,40)+'..."): '+state[g.n].note.trim());
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
})();</script>'''

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--job", default=None, help="job name for id + message (default: folder name)")
    ap.add_argument("--out", default=None, help="write to file (default: stdout)")
    a = ap.parse_args()
    out = build(a.job_dir, a.job)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out); print(f"wrote {len(out)} chars -> {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(out)
    # Also emit the VERIFIED preview link to paste above the widget — computed + existence-checked, so
    # the "Couldn't load this preview" (doubled-path) bug can't slip in by hand. Best-effort.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import style_plan_link
        job = a.job or os.path.basename(os.path.normpath(a.job_dir))
        print("\nPASTE THIS LINK DIRECTLY ABOVE THE WIDGET:\n  " + style_plan_link.emit(job), file=sys.stderr)
    except SystemExit:
        print("(no preview mp4 yet — build the cut, then: python product/style_plan_link.py <job>)", file=sys.stderr)
    except Exception:
        pass
