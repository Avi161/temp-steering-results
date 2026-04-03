"""
Phase 3: Map scored_results.json back to index.html.
Updates D.scores values and adds D.reasoning, then patches rmb() to render reasoning.
"""
import json
import re
from pathlib import Path

BASE = Path(__file__).parent
MAPPING_FILE = BASE / "id_mapping.json"
SCORED_FILE = BASE / "scored_results.json"
HTML_FILE = BASE / "index.html"

# ── 1. Load and join results ──────────────────────────────────────────────────

with open(MAPPING_FILE) as f:
    id_mapping = json.load(f)  # uuid -> eval_id (e.g. "19-25-0-lt")

with open(SCORED_FILE) as f:
    scored = json.load(f)  # [{id, score, reasoning}, ...]

# Build lookup: (layer, alpha, prompt_index, condition) -> {score, reasoning}
new_data: dict = {}
for r in scored:
    uid = r["id"]
    eval_id = id_mapping[uid]
    parts = eval_id.rsplit("-", 1)          # split on last '-' to get condition
    condition = parts[1]                    # b / lt / im
    coords = parts[0].split("-")            # layer, alpha, prompt_index
    layer, alpha, pi = int(coords[0]), int(coords[1]), int(coords[2])
    key = (layer, alpha, pi)
    if key not in new_data:
        new_data[key] = {}
    new_data[key][condition] = {"score": r["score"], "reasoning": r["reasoning"]}

print(f"Loaded data for {len(new_data)} (layer, alpha, pi) configs")

# ── 2. Parse D from index.html ────────────────────────────────────────────────

with open(HTML_FILE) as f:
    html = f.read()

# Locate `const D = {...};` — the blob may be very long; use a balanced-brace scan
D_START = html.index("const D = ") + len("const D = ")
depth = 0
i = D_START
while i < len(html):
    if html[i] == "{":
        depth += 1
    elif html[i] == "}":
        depth -= 1
        if depth == 0:
            D_END = i + 1
            break
    i += 1

D_json_str = html[D_START:D_END]
D = json.loads(D_json_str)
print(f"Parsed D.scores: {len(D['scores'])} entries")

# ── 3. Update D.scores and build D.reasoning ──────────────────────────────────

reasoning_list = []
for score_entry in D["scores"]:
    l, a, pi = score_entry["l"], score_entry["a"], score_entry["pi"]
    key = (l, a, pi)
    if key not in new_data:
        print(f"  WARNING: no new data for {key}, skipping")
        continue
    cdata = new_data[key]

    # Update scores for each condition present
    for cond in ("b", "lt", "im"):
        if cond in cdata:
            score_entry[cond] = cdata[cond]["score"]
        # If condition missing (degenerated), leave existing value (null or original)

    # Build reasoning entry
    r_entry = {"l": l, "a": a, "pi": pi}
    for cond, suffix in [("b", "b_r"), ("lt", "lt_r"), ("im", "im_r")]:
        r_entry[suffix] = cdata[cond]["reasoning"] if cond in cdata else None
    reasoning_list.append(r_entry)

D["reasoning"] = reasoning_list
print(f"Built D.reasoning: {len(reasoning_list)} entries")

# ── 4. Serialize D back into HTML ─────────────────────────────────────────────

new_D_json = json.dumps(D, separators=(",", ":"), ensure_ascii=False)
html = html[:D_START] + new_D_json + html[D_END:]

# ── 5. Patch JS: expose reasoning lookup + update rmb() ──────────────────────

# Add a helper to look up reasoning right after D is defined.
# We insert after the `const D = ...;` line.
REASONING_LOOKUP_JS = """
        /* Reasoning lookup (injected by 03_reintegrate.py) */
        const RN = {};
        (D.reasoning || []).forEach(r => { RN[r.l+'-'+r.a+'-'+r.pi] = r; });
        function getReason(l,a,pi,t) { const e=RN[l+'-'+a+'-'+pi]; if(!e)return ''; const k={b:'b_r',lt:'lt_r',im:'im_r'}[t]; return e&&e[k]?e[k]:''; }
"""

# Find where const D assignment ends (first semicolon after D_json block)
d_decl_end = html.index("const D = ") + len("const D = ")
# advance past the json blob to find the `;`
depth = 0
j = d_decl_end
while j < len(html):
    if html[j] == "{":
        depth += 1
    elif html[j] == "}":
        depth -= 1
        if depth == 0:
            j += 1  # past the closing brace
            break
    j += 1
# j now points right after the `}` of the D JSON blob; skip whitespace and `;`
while j < len(html) and html[j] in " \t\r\n;":
    j += 1
# Insert after the semicolon
semi_pos = html.rindex(";", d_decl_end, j) + 1
html = html[:semi_pos] + "\n" + REASONING_LOOKUP_JS + html[semi_pos:]

# Now patch rmb() to append the reasoning sentence after the score badge.
# Original line (single occurrence):
OLD_RMB_LINE = (
    "body.innerHTML = '<div class=\"score-badge\" style=\"color:' + col + ';background:' + bg + '\">Score: ' + score + '</div>"
    "<div class=\"response-text\">' + esc(txt) + '</div>';"
)
NEW_RMB_LINE = (
    "const reason = getReason(_ml,_ma,_mp,_mt);"
    "\n            const reasonHtml = reason ? '<p class=\"eval-reasoning\" style=\"color:var(--fg3);font-style:italic;font-size:0.85rem;margin:6px 0 0 0;line-height:1.4\">' + esc(reason) + '</p>' : '';"
    "\n            body.innerHTML = '<div class=\"score-badge\" style=\"color:' + col + ';background:' + bg + '\">Score: ' + score + '</div>' + reasonHtml + '<div class=\"response-text\">' + esc(txt) + '</div>';"
)

if OLD_RMB_LINE not in html:
    print("ERROR: Could not find rmb() line to patch — check HTML for changes")
    raise SystemExit(1)

html = html.replace(OLD_RMB_LINE, NEW_RMB_LINE, 1)
print("Patched rmb() to render reasoning")

# ── 6. Save ───────────────────────────────────────────────────────────────────

with open(HTML_FILE, "w") as f:
    f.write(html)

print(f"\nSaved updated {HTML_FILE.name}")
print("Verification: open index.html in a browser and click any heatmap cell.")
