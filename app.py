import json
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

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
        "salesforce":       "1209895234740542",
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

    # -------- Project routing --------
    title_lower = doc_title.lower()
    asana_project_id = ""
    for keyword, pid in PROJECT_MAP.items():
        if keyword in title_lower:
            asana_project_id = pid
            break
    if not asana_project_id:
        asana_project_id = CATCHALL_PROJECT_ID

    # -------- Section name --------
    section_date = ""
    if meeting_date_str:
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
    block = re.sub(rf'\s+(?={OWNER}\s*:\s*)', '\n- ', block)
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

        # Owner header takes priority - catches "Name:" on its own line
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
            # Check if bullet itself starts with an owner
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

    result = {
        "overview_text":         (overview or '').strip(),
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
    }

    return jsonify(result), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
