import json
import re
import os                                          # NEW
import requests                                    # NEW
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# NEW - Claude API call to generate Dex note summary
def generate_dex_summary(overview_text, meeting_title, doc_url):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not overview_text:
        fallback = (overview_text or "")[:400].strip()
        return f"{fallback}\n\n{doc_url}" if doc_url else fallback

    prompt = (
        f"You are summarizing a business meeting for a personal CRM note. "
        f"Write exactly 3-4 sentences summarizing the key discussion points and outcomes from this meeting overview. "
        f"Be specific and factual. Do not use bullet points. Plain prose only.\n\n"
        f"Meeting: {meeting_title}\n\n"
        f"Overview:\n{overview_text}"
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        data = resp.json()
        summary = data["content"][0]["text"].strip()
    except Exception:
        summary = (overview_text or "")[:400].strip()

    # Append the doc link
    if doc_url:
        summary = f"{summary}\n\nMeeting summary: {doc_url}"   # NEW

    return summary


@app.route('/parse', methods=['POST'])
def parse():
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    text             = (body.get('raw') or '').strip()
    self_email       = (body.get('self_email') or '').lower().strip()
    doc_title        = (body.get('doc_title') or '').strip()
    meeting_date_str = (body.get('meeting_date') or '').strip()
    doc_url          = (body.get('doc_url') or '').strip()

    if not text:
        return jsonify({"error": "Field 'raw' is required and was empty"}), 400

    # -------- PROJECT LOOKUP TABLE --------
    PROJECT_MAP = {

        "consensus":        "1212896479276968",
        "fidelity":         "1213402351644423",
        "servicenow":       "1213426227880237",
        "sora":             "1213367830867287",
        "microsoft":        "1210069349567014",
        "workday":          "1210895097690192",
        "uipath":           "1209967758013887",
        "bombora":          "1209906059708631",
        "amperity":         "1209878243266352",
        "nutanix":          "1209904779807372",
        "fortinet":         "1209904779807349",
        "planview":         "1209904779807340",
        "juniper":          "1209904779807381",
        "hpe":              "1209866692256215",
        "aws":              "1209833262475732",
        "accenture":        "1209833262475698",
        "ifs":              "1209878243266367",
        "f5":               "1210376082717082",
        "konica":           "1210376015464430",
        "fis":              "1210093465965056",
        "kellogg":          "1210607165419426",
        "selling systems":  "1212466307851908",
        "stage 2":          "1210376302975806",
        "stage-2":          "1210376302975806",
        "nac":              "1209713385820861",
        "national ability": "1209713385820861",
        "accord":           "1209761576173351",
        "inaccord":         "1209761576173351",
        "angela":           "1209738855279618",
        "revolear":         "1210088476509780",
        "arkestro":         "1212501263453507",
        "pathfactory":      "1209961909785004",
        "anysoft":          "1213426111951560",
        "blindit":          "1210912320853707",
    }

    CATCHALL_PROJECT_ID   = "1209675753214645"
    SCOTT_USER_GID        = "1208535971146001"
    SCOTT_NAMES           = {"scott", "scott barghaan", "scott b"}
    OTHER_OWNER_FIELD_GID = "1210898742771365"

    # -------- EMAIL DOMAIN LOOKUP TABLE --------
    DOMAIN_MAP = {
        "goconsensus.com":    "1212896479276968",
        # salesforce.com removed - routed by named email instead
        "databook.com":       "1209694673930748",
        "microsoft.com":      "1210069349567014",
        "workday.com":        "1210895097690192",
        "servicenow.com":     "1213426227880237",
        "uipath.com":         "1209967758013887",
        "bombora.com":        "1209906059708631",
        "amperity.com":       "1209878243266352",
        "nutanix.com":        "1209904779807372",
        "fortinet.com":       "1209904779807349",
        "planview.com":       "1209904779807340",
        "juniper.net":        "1209904779807381",
        "hpe.com":            "1209866692256215",
        "amazonaws.com":      "1209833262475732",
        "accenture.com":      "1209833262475698",
        "ifs.com":            "1209878243266367",
        "f5.com":             "1210376082717082",
        "konicaminolta.com":  "1210376015464430",
        "fisglobal.com":      "1210093465965056",
        "fidelity.com":       "1213402351644423",
        "inaccord.com":       "1209761576173351",
        "accord.com":         "1209761576173351",
        "stage2capital.com":  "1210376302975806",
        "discovernac.org":    "1209713385820861",
        "kellogg.northwestern.edu": "1210607165419426",
        "sora.com":           "1213367830867287",
        "revolear.com":       "1210088476509780",
        "arkestro.com":       "1212501263453507",
        "pathfactory.com":    "1209961909785004",
        "anysoft.com":        "1213426111951560",
        "blindit.org":        "1210912320853707",
    }

    MY_NETWORK_PROJECT_ID = "1210376255146963"

    # -------- Named email overrides --------
    EMAIL_MAP = {
        "russell.scherwin@outlook.com": "1213546899146018",   # Russ Sherwin - Other Network
        "juliavp27@yahoo.com":          "1213546903950732",   # Julia Vander Plough
        "mkrejcova@salesforce.com":     "1213546921820103",   # M. Krejcova - Salesforce
        "verma.s@salesforce.com":       "1210912320853707",   # S. Verma - Salesforce
        "ryan.crombeen@salesforce.com": "1210376255146963",   # Ryan Crombeen - Salesforce
    }

    # -------- Project routing --------
    all_emails = re.findall(r'[\w.\-+%]+@[\w.\-]+\.\w+', text, flags=re.I)
    skip = {self_email, 'meetings@fireflies.ai', 'team@fireflies.ai'}
    attendee_emails = [e for e in all_emails if e.lower() not in skip]

    asana_project_id = ""

    for email in attendee_emails:
        if email.lower() in EMAIL_MAP:
            asana_project_id = EMAIL_MAP[email.lower()]
            break

    if not asana_project_id:
        for email in attendee_emails:
            domain = email.split('@')[-1].lower()
            if domain in DOMAIN_MAP:
                asana_project_id = DOMAIN_MAP[domain]
                break

    if not asana_project_id:
        title_lower = doc_title.lower()
        for keyword, pid in PROJECT_MAP.items():
            if keyword in title_lower:
                asana_project_id = pid
                break

    if not asana_project_id:
        personal_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"}
        has_only_personal = all(
            e.split('@')[-1].lower() in personal_domains
            for e in attendee_emails
        ) if attendee_emails else False
        asana_project_id = MY_NETWORK_PROJECT_ID if has_only_personal else CATCHALL_PROJECT_ID

    # -------- Section name --------
    section_date = ""
    date_match = re.search(
        r'Date:\s*([A-Za-z]+ \d{1,2},\s*\d{4})',
        meeting_date_str, re.IGNORECASE
    )
    if date_match:
        try:
            dt = datetime.strptime(date_match.group(1).strip(), "%B %d, %Y")
            section_date = dt.strftime("%b %d, %Y")
        except ValueError:
            pass
    if not section_date and meeting_date_str:
        for fmt in ("%B %d, %Y %I:%M %p %Z", "%B %d, %Y %I:%M %p", "%B %d, %Y"):
            try:
                cleaned = (meeting_date_str
                           .replace(" EST","").replace(" PST","")
                           .replace(" CST","").replace(" MST","").strip())
                dt = datetime.strptime(cleaned, fmt)
                section_date = dt.strftime("%b %d, %Y")
                break
            except ValueError:
                continue

    section_name = doc_title if doc_title else "Meeting"
    if section_date:
        section_name = f"{section_name} - {section_date}"

    # -------- Due dates --------
    meeting_dt = None
    if meeting_date_str:
        for fmt in ("%B %d, %Y %I:%M %p %Z", "%B %d, %Y %I:%M %p", "%B %d, %Y"):
            try:
                cleaned = (meeting_date_str
                           .replace(" EST","").replace(" PST","")
                           .replace(" CST","").replace(" MST","").strip())
                meeting_dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
    if not meeting_dt:
        meeting_dt = datetime.utcnow()

    scott_due_date  = (meeting_dt + timedelta(hours=48)).strftime("%Y-%m-%d")
    others_due_date = (meeting_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    # -------- Normalize text --------
    t = text.replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ')
    t = re.sub(r'^\s*[•\u2022\u2023\u25E6\u2043\u2212\u2013\u2014-]\s*', '- ', t, flags=re.M)

    # -------- Section finders --------
    def find_section(src, keys, next_keys=None):
        matches = []
        for k in keys:
            h = re.compile(r'(?im)^\s*(?:\d+\.\s*)?' + re.escape(k) + r'\b\s*[:\-]?\s*$')
            m = h.search(src)
            if m:
                matches.append((m.start(), m.end()))
        if matches:
            _, start = sorted(matches, key=lambda x: x[0])[0]
            end = len(src)
            if next_keys:
                nxt = re.compile(r'(?im)^\s*(?:\d+\.\s*)?(?:' + '|'.join(re.escape(k) for k in next_keys) + r')\b\s*[:\-]?\s*$')
                m2 = nxt.search(src, start)
                if m2:
                    end = m2.start()
            return src[start:end].strip()
        same = re.compile(r'(?is)\b(?:' + '|'.join(re.escape(k) for k in keys) + r')\b\s*[:\-]?\s*(.+?)(?:\n{2,}|$)')
        m = same.search(src)
        return m.group(1).strip() if m else ""

    overview_keys = ['overview', 'executive summary', 'summary', 'highlights', 'recap']
    action_keys   = ['action items', 'next steps', 'actions', 'tasks', 'to-dos', 'todos']
    barriers      = ['notes', 'action items', 'next steps', 'actions', 'tasks',
                     'to-dos', 'todos', 'participants', 'attendees', 'people']

    overview      = find_section(t, overview_keys, next_keys=barriers)
    actions_block = find_section(t, action_keys)

    # -------- Email extraction --------
    emails = re.findall(r'[\w.\-+%]+@[\w.\-]+\.\w+', t, flags=re.I)
    seen, uniq = set(), []
    for e in emails:
        el = e.lower()
        if el not in seen:
            seen.add(el)
            uniq.append(e)
    drop = {self_email, 'meetings@fireflies.ai', 'team@fireflies.ai'}
    uniq = [e for e in uniq if e.lower() not in drop]

    # -------- Parse action items --------
    OWNER     = r'(?:[A-Z][\w\'\-]+(?: [A-Z][\w\'\-]+){1,3})'
    VERB_LIST = ['Introduce', 'Send', 'Share', 'Update', 'Continue', 'Invite', 'Consider',
                 'Keep', 'Connect', 'Schedule', 'Review', 'Provide', 'Prepare', 'Research',
                 'Explore', 'Develop', 'Draft', 'Follow']
    VERB = r'(?:' + '|'.join(VERB_LIST) + r')'

    block = (actions_block or '').strip()
    block = re.sub(r'\s-\s+(?=[\[\(]?[A-Z])', '\n- ', block)
    block = re.sub(r'\s[•\u2022]\s+(?=[\[\(]?[A-Z])', '\n- ', block)
    block = re.sub(rf'\s+(?={OWNER}\s+{VERB}\b)', '\n- ', block)

    items      = []
    curr_owner = None
    curr_task  = None

    owner_header_pat = re.compile(rf'^\s*(?!- )(?P<owner>{OWNER})\s*:\s*$')
    bullet_pat       = re.compile(r'^\s*-\s*(.+)$')
    inline_bracket   = re.compile(rf'^\[(?P<owner>{OWNER})\]\s*(?P<rest>.+)$')
    inline_colon     = re.compile(rf'^(?P<owner>{OWNER})\s*:\s*(?P<rest>.+)$')
    inline_bare      = re.compile(rf'^(?P<owner>{OWNER})\s+(?P<rest>{VERB}\b.+)$')

    for ln in block.split('\n'):
        s = ln.strip()
        if not s:
            continue

        m_o = owner_header_pat.match(ln)
        if m_o:
            if curr_task:
                items.append((curr_owner, curr_task.strip()))
                curr_task = None
            curr_owner = m_o.group('owner').strip()
            continue

        m_b = bullet_pat.match(ln)
        if m_b:
            if curr_task:
                items.append((curr_owner, curr_task.strip()))
            curr_task = m_b.group(1).strip()
            m_inline = (inline_bracket.match(curr_task) or
                        inline_colon.match(curr_task) or
                        inline_bare.match(curr_task))
            if m_inline:
                curr_owner = m_inline.group('owner').strip()
                curr_task  = m_inline.group('rest').strip()
            continue

        if curr_task:
            curr_task += ' ' + s
        else:
            curr_task = s

    if curr_task:
        items.append((curr_owner, curr_task.strip()))

    # -------- Post-split --------
    final_items = []
    splitter = re.compile(rf'\s+(?=(?:{OWNER}\s*:\s*|{OWNER}\s+{VERB}\b|{VERB}\b))')

    for own, task in items:
        chunks = [c.strip(' ;.-') for c in splitter.split(task) if c.strip(' ;.-')]
        for ch in chunks:
            m_inline = (inline_bracket.match(ch) or
                        inline_colon.match(ch) or
                        inline_bare.match(ch))
            if m_inline:
                final_items.append((m_inline.group('owner').strip(), m_inline.group('rest').strip()))
            else:
                final_items.append((own, ch))

    # -------- Build task objects --------
    task_objects = []
    for own, task in final_items:
        owner_lower = (own or '').lower().strip()
        if owner_lower in SCOTT_NAMES:
            assignee_gid = SCOTT_USER_GID
            other_owner  = ""
            due_date     = scott_due_date
        elif own:
            assignee_gid = ""
            other_owner  = own
            due_date     = others_due_date
        else:
            assignee_gid = ""
            other_owner  = ""
            due_date     = others_due_date

        task_objects.append({
            "name":         task,
            "assignee_gid": assignee_gid,
            "other_owner":  other_owner,
            "due_date":     due_date,
            "notes":        f"Meeting summary: {doc_url}" if doc_url else "",
        })

    # -------- Build email bullets --------
    plain_lines = []
    html_lines  = []
    for own, task in final_items:
        if own:
            plain_lines.append(f"- [{own}] {task}")
            html_lines.append(f"<li><b>{own}:</b> {task}</li>")
        else:
            plain_lines.append(f"- {task}")
            html_lines.append(f"<li>{task}</li>")

    # -------- Build overview HTML --------
    overview_html_lines = []
    for line in (overview or '').strip().split('\n'):
        line = line.strip().lstrip('- ').strip()
        if ':' in line:
            label, rest = line.split(':', 1)
            overview_html_lines.append(f"<li><b>{label.strip()}:</b>{rest}</li>")
        elif line:
            overview_html_lines.append(f"<li>{line}</li>")
    overview_html = "".join(overview_html_lines)

    # NEW - Generate Dex note (Claude summary + doc link)
    dex_note = generate_dex_summary(overview, doc_title, doc_url)

    # NEW - Clean attendee email list for Dex lookups (exclude self + Fireflies system emails)
    dex_attendee_emails = [e for e in uniq if e.lower() not in drop]

    result = {
        "overview_text":         (overview or '').strip(),
        "overview_html":          overview_html,
        "action_items_bullets":  "\n".join(plain_lines).strip(),
        "items_html":            "".join(html_lines),
        "emails_joined":         ", ".join(uniq),
        "asana_project_id":      asana_project_id,
        "section_name":          section_name,
        "task_objects":          task_objects,
        "task_objects_json":     json.dumps(task_objects),
        "scott_due_date":        scott_due_date,
        "others_due_date":       others_due_date,
        "other_owner_field_gid": OTHER_OWNER_FIELD_GID,
        "dex_note":              dex_note,              # NEW
        "dex_attendee_emails":   dex_attendee_emails,  # NEW
    }

    return jsonify(result), 200

@app.route('/coaching-rollup', methods=['POST'])
def coaching_rollup():
    try:
        body = request.get_json(silent=True, force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    ledger = (body.get('ledger') or '').strip()
    emails = (body.get('emails') or '').strip()

    if not emails:
        return jsonify({"error": "Field 'emails' is required and was empty"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

    prompt = (
        f"You are a coaching analyst synthesizing weekly meeting coaching data for Scott Barghaan. "
        f"Here is Scott's persistent coaching ledger: <ledger>{ledger}</ledger> "
        f"Here are this week's Fireflies coaching email summaries: <this_week>{emails}</this_week> "
        f"Your job: "
        f"1. Identify which existing patterns from the ledger appeared this week and increment their count. "
        f"2. Identify any new patterns not in the ledger. "
        f"3. Note which strengths showed up. "
        f"4. Check whether last week's active focus moved. "
        f"5. Set next week's focus - one thing only. "
        f"6. Compute average scores across this week's meetings for all 5 dimensions. "
        f"Return ONLY raw JSON, no preamble, no markdown, no backticks, nothing before or after the opening curly brace. "
        f'Use this exact structure: {{"week_label":"Apr 7-13","meetings_reviewed":3,"scores":{{"listening":3.7,"questions":3.3,"advice_timing":3.7,"situational_read":4.0,"restraint":3.3,"avg":3.6}},"patterns":[{{"name":"Solution jump","status":"recurring","appeared_this_week":true,"meetings_this_week":2,"total_meeting_count":16,"last_seen":"Apr 9"}}],"strengths_this_week":["Situational read","Framing strategy before tactics"],"focus_last_week":"Confirm before committing","focus_movement":"Partial - appeared in 1 of 3 meetings vs 2 of 3 last week","focus_next_week":"One sharp diagnostic question before any offer - every time","high_five":"Situational read scored 4+ across all 3 meetings - that is 5 straight weeks at this level. It is a real strength not a fluke.","nudge":"Solution jump appeared again in 2 of 3 meetings. The pattern is not a habit issue - it is a structure issue. Add one question before any offer and make it non-negotiable.","one_line_summary":"Strong read of the room still moving too fast once you see the path."}}'
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=55,
        )
        data = resp.json()
        response_text = data["content"][0]["text"].strip()
    except Exception as e:
        return jsonify({"error": f"Claude API call failed: {str(e)}"}), 500

    try:
        parsed = json.loads(response_text)
        return jsonify({"success": True, "data": parsed}), 200
    except json.JSONDecodeError:
        return jsonify({"success": False, "raw": response_text}), 200

@app.route('/extract-notion-blocks', methods=['POST'])
def extract_notion_blocks():
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    blocks = body.get('blocks', [])
    lines = []

    for block in blocks:
        block_type = block.get('type', '')
        type_data = block.get(block_type, {})
        rich_text = type_data.get('rich_text', [])
        text = ''.join([rt.get('plain_text', '') for rt in rich_text])
        if text.strip():
            lines.append(text.strip())

    return jsonify({"text": "\n".join(lines)}), 200

@app.route('/get-ledger', methods=['GET', 'POST'])
def get_ledger():
    notion_token = os.environ.get('NOTION_TOKEN', '')
    page_id = '3404d02e-d005-8195-a595-f5e132e663d2'

    if not notion_token:
        return jsonify({"error": "NOTION_TOKEN not set"}), 500

    try:
        resp = requests.get(
            f'https://api.notion.com/v1/blocks/{page_id}/children',
            headers={
                'Authorization': f'Bearer {notion_token}',
                'Notion-Version': '2022-06-28',
            },
            timeout=30,
        )
        data = resp.json()
        blocks = data.get('results', [])
        lines = []

        for block in blocks:
            block_type = block.get('type', '')
            type_data = block.get(block_type, {})
            rich_text = type_data.get('rich_text', [])
            text = ''.join([rt.get('plain_text', '') for rt in rich_text])
            if text.strip():
                lines.append(text.strip())

        return jsonify({"text": "\n".join(lines)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)