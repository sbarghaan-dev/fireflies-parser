#!/usr/bin/env python3
"""
Render the routing pre-flight artifact HTML from:
  preflight.json   (output of route_check.py)
  owner_check.json (pid -> {name, has_other_owner})  built from Asana get_project
  meta.json        (generated_at, week_label, freshness, task_id)
Writes self-contained, light-mode HTML to stdout.
"""
import json, sys, html

pf = json.load(open("preflight.json"))
oc = json.load(open("owner_check.json"))
meta = json.load(open("meta.json"))

c = pf["counts"]
gaps = pf["gaps"]
covered = pf["covered"]
personal = pf["personal_only"]
fresh = meta["freshness"]
task_id = meta.get("task_id", "")

owner_gaps = {pid: v for pid, v in oc.items() if not v.get("has_other_owner")}

def esc(s): return html.escape(str(s))

total_problems = len(gaps) + len(owner_gaps)
if total_problems == 0:
    verdict_class, verdict_txt = "ok", "In sync. No routing gaps, no missing Other Owner fields next week."
else:
    bits = []
    if gaps: bits.append(f"{len(gaps)} routing gap{'s' if len(gaps)!=1 else ''}")
    if owner_gaps: bits.append(f"{len(owner_gaps)} project{'s' if len(owner_gaps)!=1 else ''} missing Other Owner")
    verdict_class, verdict_txt = "warn", " &middot; ".join(bits) + " need attention before next week."

fresh_class = "ok" if fresh.get("in_sync") else "warn"
fresh_txt = esc(fresh.get("note","")) + (f" (local {esc(fresh.get('local_head',''))})" if fresh.get("local_head") else "")

def rows_gaps():
    if not gaps:
        return '<tr><td colspan="4" class="empty">No meetings hit the catchall this week.</td></tr>'
    out=[]
    for g in gaps:
        fix = f"<span class='tag'>{esc(g.get('fix_where','app.py'))}</span> {esc(g.get('fix_what',''))}"
        out.append(f"<tr><td>{esc(g['start'][:16].replace('T',' '))}</td><td>{esc(g['title'])}</td><td class='mono'>{esc(', '.join(g['emails']))}</td><td class='fix'>{fix}</td></tr>")
    return "".join(out)

def rows_owner():
    out=[]
    for pid, v in oc.items():
        ok = v.get("has_other_owner")
        if ok:
            cell = "<span class='pill ok'>attached</span>"
        else:
            cell = ("<span class='pill bad'>MISSING</span>"
                    "<div class='fix'><span class='tag'>Asana</span> Open this project, add the "
                    "&quot;Other Owner&quot; custom field. No app.py change needed.</div>")
        out.append(f"<tr><td>{esc(v.get('name',pid))}</td><td class='mono'>{esc(pid)}</td><td>{cell}</td></tr>")
    return "".join(out) or '<tr><td colspan="3" class="empty">No projects routed to this week.</td></tr>'

def rows_covered():
    out=[]
    for m in covered:
        reason = m["reason"].split(":",1)
        rtype = reason[0]; detail = reason[1] if len(reason)>1 else ""
        out.append(f"<tr><td>{esc(m['start'][:16].replace('T',' '))}</td><td>{esc(m['title'])}</td><td><span class='tag'>{esc(rtype)}</span> <span class='mono'>{esc(detail)}</span></td></tr>")
    return "".join(out) or '<tr><td colspan="3" class="empty">None.</td></tr>'

def rows_personal():
    out=[]
    for m in personal:
        out.append(f"<tr><td>{esc(m['start'][:16].replace('T',' '))}</td><td>{esc(m['title'])}</td><td class='mono'>{esc(', '.join(m['emails']))}</td></tr>")
    return "".join(out) or '<tr><td colspan="3" class="empty">None.</td></tr>'

rerun_btn = ""
if task_id and task_id != "TASK_ID_PLACEHOLDER":
    rerun_btn = f"""<button id="rerun" onclick="rerun()">Re-run now</button>
    <span id="rerunmsg" class="hint"></span>
    <script>
      async function rerun() {{
        const b=document.getElementById('rerun'), m=document.getElementById('rerunmsg');
        b.disabled=true; m.textContent='Started. Give it ~1 min, then hit Reload above.';
        try {{ await window.cowork.runScheduledTask('{task_id}'); }}
        catch(e) {{ m.textContent='Could not start: '+e; b.disabled=false; }}
      }}
    </script>"""

HTML = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Routing Pre-Flight</title>
<style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#f7f8fa; color:#1a1d21; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
.wrap {{ max-width:880px; margin:0 auto; padding:24px 20px 56px; }}
h1 {{ font-size:20px; margin:0 0 2px; }}
.sub {{ color:#5b6470; font-size:13px; margin-bottom:18px; }}
.verdict {{ padding:14px 16px; border-radius:10px; font-weight:600; margin-bottom:14px; }}
.verdict.ok {{ background:#e7f6ec; color:#176c3a; border:1px solid #b8e3c6; }}
.verdict.warn {{ background:#fdf0e3; color:#9a5816; border:1px solid #f3d4ad; }}
.fresh {{ font-size:13px; padding:8px 12px; border-radius:8px; margin-bottom:22px; }}
.fresh.ok {{ background:#eef2f6; color:#3a4350; }}
.fresh.warn {{ background:#fbe6e6; color:#9a1616; border:1px solid #f0bcbc; font-weight:600; }}
.cards {{ display:flex; gap:10px; margin-bottom:24px; flex-wrap:wrap; }}
.card {{ flex:1; min-width:120px; background:#fff; border:1px solid #e4e8ee; border-radius:10px; padding:12px 14px; }}
.card .n {{ font-size:24px; font-weight:700; }}
.card .l {{ font-size:12px; color:#5b6470; text-transform:uppercase; letter-spacing:.04em; }}
.card.gap .n {{ color:#c0392b; }}
.card.ok .n {{ color:#176c3a; }}
h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.05em; color:#5b6470; margin:26px 0 8px; }}
table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #e4e8ee; border-radius:10px; overflow:hidden; }}
th,td {{ text-align:left; padding:9px 12px; border-bottom:1px solid #eef1f5; font-size:13px; vertical-align:top; }}
th {{ background:#f2f4f7; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#5b6470; }}
tr:last-child td {{ border-bottom:none; }}
.empty {{ color:#8a929c; font-style:italic; }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; color:#46506b; }}
.tag {{ display:inline-block; background:#eef2f6; color:#3a4350; border-radius:5px; padding:1px 6px; font-size:11px; font-weight:600; }}
.fix {{ font-size:12px; color:#46506b; }} .fix .tag {{ background:#fdebd0; color:#9a5816; margin-right:4px; }}
.pill {{ display:inline-block; border-radius:20px; padding:2px 10px; font-size:11px; font-weight:700; }}
.pill.ok {{ background:#e7f6ec; color:#176c3a; }}
.pill.bad {{ background:#fbe6e6; color:#c0392b; }}
details {{ margin-top:6px; }} summary {{ cursor:pointer; color:#5b6470; font-size:13px; }}
.actions {{ margin-top:26px; }}
button {{ background:#1a1d21; color:#fff; border:none; border-radius:8px; padding:9px 16px; font-size:13px; font-weight:600; cursor:pointer; }}
button:disabled {{ opacity:.5; cursor:default; }}
.hint {{ color:#5b6470; font-size:12px; margin-left:10px; }}
</style></head>
<body><div class="wrap">
  <h1>Fireflies Routing Pre-Flight</h1>
  <div class="sub">Week of {esc(meta['week_label'])} &middot; generated {esc(meta['generated_at'])}</div>

  <div class="verdict {verdict_class}">{verdict_txt}</div>
  <div class="fresh {fresh_class}">Clone freshness: {fresh_txt}</div>

  <div class="cards">
    <div class="card"><div class="n">{c['covered']}</div><div class="l">Covered</div></div>
    <div class="card {'gap' if gaps else 'ok'}"><div class="n">{c['gaps']}</div><div class="l">Routing gaps</div></div>
    <div class="card {'gap' if owner_gaps else 'ok'}"><div class="n">{len(owner_gaps)}</div><div class="l">Owner-field gaps</div></div>
    <div class="card"><div class="n">{c['personal_only']}</div><div class="l">Personal-only</div></div>
  </div>

  <h2>Routing gaps (would hit catchall)</h2>
  <table><thead><tr><th>When</th><th>Meeting</th><th>Attendees</th><th>Where to fix</th></tr></thead><tbody>{rows_gaps()}</tbody></table>

  <h2>Other Owner field check &mdash; routed projects</h2>
  <table><thead><tr><th>Project</th><th>ID</th><th>Other Owner</th></tr></thead><tbody>{rows_owner()}</tbody></table>

  <h2>Covered meetings</h2>
  <table><thead><tr><th>When</th><th>Meeting</th><th>Routed via</th></tr></thead><tbody>{rows_covered()}</tbody></table>

  <details><summary>Personal-only meetings ({c['personal_only']}) &mdash; route to My Network, no action needed</summary>
  <table style="margin-top:8px"><thead><tr><th>When</th><th>Meeting</th><th>Attendees</th></tr></thead><tbody>{rows_personal()}</tbody></table>
  </details>

  <div class="actions">{rerun_btn}</div>
</div></body></html>"""

sys.stdout.write(HTML)
