#!/usr/bin/env python3
"""
Weekly routing pre-flight: simulate the fireflies-parser app.py routing logic
against next week's Google Calendar, surface gaps + projects to verify.

Inputs:
  --app    path to app.py (local clone)
  --cal    path to the saved list_events JSON
Output: JSON to stdout (machine-readable) + a human summary to stderr.

Mirrors app.py routing order exactly:
  1. EMAIL_MAP exact email match (first attendee match wins)
  2. DOMAIN_MAP suffix match
  3. PROJECT_MAP title keyword substring
  4. catchall: all-personal -> My Network; else -> catchall (this is a GAP)

KNOWN APPROXIMATION: the live parser reads attendee emails from the Fireflies
transcript text in order of appearance. This sim uses calendar attendee order.
For a meeting with two EMAIL_MAP-mapped attendees, the "first match wins"
winner can differ. Reliable for catchall detection + Other Owner checks.
"""
import ast, json, sys, argparse

SCOTT_EMAILS = {"sbarghaan@gmail.com", "scott@barghaan.com"}
FIREFLIES_BOTS = {"meetings@fireflies.ai", "team@fireflies.ai"}

def extract_dicts(app_path):
    """AST-parse app.py and pull the routing tables regardless of nesting."""
    src = open(app_path).read()
    tree = ast.parse(src)
    wanted_dicts = {"EMAIL_MAP", "DOMAIN_MAP", "PROJECT_MAP"}
    wanted_consts = {"CATCHALL_PROJECT_ID", "MY_NETWORK_PROJECT_ID", "OTHER_OWNER_FIELD_GID"}
    out = {}
    personal = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    if t.id in wanted_dicts:
                        try: out[t.id] = ast.literal_eval(node.value)
                        except Exception: pass
                    elif t.id in wanted_consts:
                        try: out[t.id] = ast.literal_eval(node.value)
                        except Exception: pass
                    elif t.id == "personal_domains":
                        try: personal = set(ast.literal_eval(node.value))
                        except Exception: pass
    out["personal_domains"] = personal or {"gmail.com","yahoo.com","hotmail.com","outlook.com","icloud.com"}
    out["EMAIL_MAP"] = {k.lower(): v for k, v in out.get("EMAIL_MAP", {}).items()}
    out["DOMAIN_MAP"] = {k.lower(): v for k, v in out.get("DOMAIN_MAP", {}).items()}
    return out

def simulate(emails, title, maps):
    """Return (project_id, reason) using app.py's exact order."""
    for e in emails:
        if e.lower() in maps["EMAIL_MAP"]:
            return maps["EMAIL_MAP"][e.lower()], f"EMAIL_MAP:{e.lower()}"
    for e in emails:
        dom = e.split("@")[-1].lower()
        if dom in maps["DOMAIN_MAP"]:
            return maps["DOMAIN_MAP"][dom], f"DOMAIN_MAP:{dom}"
    tl = (title or "").lower()
    for kw, pid in maps["PROJECT_MAP"].items():
        if kw in tl:
            return pid, f"PROJECT_MAP:'{kw}'"
    if emails and all(e.split("@")[-1].lower() in maps["personal_domains"] for e in emails):
        return maps["MY_NETWORK_PROJECT_ID"], "CATCHALL:personal->MyNetwork"
    return maps["CATCHALL_PROJECT_ID"], "CATCHALL:GAP"

def suggest_fix(emails, maps):
    """Tell Scott exactly where + what to fix for a routing gap. Always an app.py edit."""
    personal = maps["personal_domains"]
    nonp = [e for e in emails if e.split("@")[-1].lower() not in personal]
    doms = sorted({e.split("@")[-1].lower() for e in nonp})
    if len(doms) == 1:
        return (f"Add DOMAIN_MAP['{doms[0]}'] -> <project_id> (covers everyone at that domain), "
                f"or an EMAIL_MAP entry for the specific contact. If the target project is new, "
                f"create it in Asana with the Other Owner field first, then add its ID here.")
    if nonp:
        return (f"Add EMAIL_MAP entries for {', '.join(nonp)} -> <project_id>, or a PROJECT_MAP "
                f"title keyword if the meeting name is distinctive. Create the Asana project "
                f"+ Other Owner field if it does not exist yet.")
    return ("Add a PROJECT_MAP title keyword -> <project_id> (all attendees are on personal "
            "domains). Create the Asana project + Other Owner field if new.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--cal", required=True)
    args = ap.parse_args()

    maps = extract_dicts(args.app)
    cal = json.load(open(args.cal))
    events = cal.get("events", [])

    covered, personal_only, gaps, skipped = [], [], [], []
    routed_projects = {}  # pid -> list of meeting titles

    for ev in events:
        title = ev.get("summary", "(no title)")
        start = (ev.get("start", {}) or {}).get("dateTime") or (ev.get("start", {}) or {}).get("date", "")
        atts = ev.get("attendees", []) or []
        ext = []
        for a in atts:
            em = (a.get("email") or "").lower()
            if not em: continue
            if a.get("self"): continue
            if em in SCOTT_EMAILS or em in FIREFLIES_BOTS: continue
            ext.append(em)
        rec = {"title": title, "start": start, "emails": ext}
        if not ext:
            skipped.append(rec); continue
        pid, reason = simulate(ext, title, maps)
        rec["project_id"], rec["reason"] = pid, reason
        if reason == "CATCHALL:GAP":
            rec["fix_where"] = "app.py"
            rec["fix_what"] = suggest_fix(ext, maps)
            gaps.append(rec)
        elif reason.startswith("CATCHALL:personal"):
            personal_only.append(rec)
        else:
            covered.append(rec)
            routed_projects.setdefault(pid, []).append(title)

    result = {
        "week_summary": cal.get("summary"),
        "counts": {"covered": len(covered), "personal_only": len(personal_only),
                   "gaps": len(gaps), "skipped_no_attendees": len(skipped),
                   "total_events": len(events)},
        "gaps": gaps,
        "covered": covered,
        "personal_only": personal_only,
        "distinct_routed_projects": sorted(routed_projects.keys()),
        "other_owner_field_gid": maps.get("OTHER_OWNER_FIELD_GID"),
    }
    print(json.dumps(result, indent=2))

    c = result["counts"]
    print(f"\n=== ROUTING PRE-FLIGHT: {result['week_summary']} ===", file=sys.stderr)
    print(f"Covered: {c['covered']} | Personal-only: {c['personal_only']} | GAPS: {c['gaps']} | (skipped, no attendees: {c['skipped_no_attendees']})", file=sys.stderr)
    if gaps:
        print("\n--- GAPS (would hit catchall) ---", file=sys.stderr)
        for g in gaps:
            print(f"  [{g['start'][:16]}] {g['title']}  ->  {g['emails']}", file=sys.stderr)
    print(f"\nDistinct routed projects to verify Other Owner: {len(result['distinct_routed_projects'])}", file=sys.stderr)

if __name__ == "__main__":
    main()
