"""Bundle all 20 answer files + trace logs + case_pack metadata into one self-contained
ui/index.html. No server, no external dependencies - open the file directly in a browser.
Run AFTER build_answer.py, write_back.py, and add_whatif_branches.py.
Run from the hhgoa folder: python build_ui.py
"""
import base64
import json
from pathlib import Path
import pandas as pd

LOGO_PATH = Path("assets/savanna-logo.png")
LOGO_DATA_URI = ""
if LOGO_PATH.exists():
    LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")

cases_meta = pd.read_csv("data/case_pack.csv").set_index("case_id")
closed_meta_df = pd.read_csv("data/closed_cases_history.csv").set_index("case_id")

# only embed metadata for closed cases actually cited by one of our 20 investigations -
# keeps the bundle small instead of shipping all 5,565 rows
_cited = set()
for p in Path("cases").glob("HHG-*.json"):
    _cited |= set(json.loads(p.read_text(encoding="utf-8"))["case"].get("similar_prior_cases", []))

CLOSED_META = {
    cid: {"outcome": str(r["outcome"]), "pattern": str(r["pattern"]),
          "exposure_usd": float(r["exposure_usd"]), "card_id": str(r["card_id"])}
    for cid, r in closed_meta_df.iterrows() if cid in _cited
}

bundle = []
for path in sorted(Path("cases").glob("HHG-*.json")):
    ans = json.loads(path.read_text(encoding="utf-8"))
    case_id = ans["case_id"]
    meta = cases_meta.loc[case_id]
    ans["_meta"] = {
        "customer_id": str(meta["customer_id"]),
        "card_id": str(meta["card_id"]),
        "trigger_type": str(meta["trigger_type"]),
        "flagged_txn_id": str(meta["flagged_txn_id"]),
    }
    trace_path = Path("logs") / f"{case_id}.trace.json"
    ans["_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))["events"] if trace_path.exists() else []
    bundle.append(ans)

DATA_JSON = json.dumps(bundle, ensure_ascii=False).replace("</script", "<\\/script")
CLOSED_META_JSON = json.dumps(CLOSED_META, ensure_ascii=False).replace("</script", "<\\/script")

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HHGOA Fraud Investigation Agent</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --bg: #f7f4ee; --bg2: #efeadf; --bg3: #e7e1d3;
  --ink: #17150f; --ink-soft: #4a453a; --muted: #8a8474;
  --accent: #ff6a1a; --accent-ink: #b8460a;
  --fraud: #b3261e; --legit: #2e6b47; --uncertain: #9a5b12;
  --hair: rgba(23,21,15,.10); --hair-soft: rgba(23,21,15,.06);
  --glass-bg: rgba(255,252,246,.55); --glass-border: rgba(23,21,15,.08);
  --sans: "Inter", -apple-system, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
::selection { background: var(--accent); color:#fff; }
::-webkit-scrollbar { width:9px; height:9px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--bg3); border-radius:5px; border:2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background:#d9d0ba; }
body {
  margin:0; color:var(--ink); font-family:var(--sans); font-size:16px; line-height:1.55;
  background:
    radial-gradient(1100px 500px at 8% -12%, rgba(255,106,26,.05), transparent 60%),
    radial-gradient(900px 420px at 100% 4%, rgba(255,106,26,.035), transparent 55%),
    var(--bg);
  -webkit-font-smoothing:antialiased;
}
header {
  padding:20px 32px; display:flex; justify-content:space-between; align-items:center;
  border-bottom:1px solid var(--hair);
  position:sticky; top:0; z-index:10;
  background:rgba(247,244,238,.72); backdrop-filter:blur(14px) saturate(140%); -webkit-backdrop-filter:blur(14px) saturate(140%);
}
.brand h1 { font-size:22px; margin:0; font-weight:700; letter-spacing:-.015em; }
.brand .sub { color:var(--muted); font-size:13px; margin-top:3px; letter-spacing:.01em; }
header .savanna { display:flex; align-items:center; gap:9px; }
header .savanna img { height:34px; display:block; }
header .savanna .label { font-size:11.5px; color:var(--muted); letter-spacing:.06em; text-transform:uppercase; font-weight:600; }
.stats { display:flex; gap:0; padding:22px 32px 24px; border-bottom:1px solid var(--hair); flex-wrap:wrap; }
.stat { padding:0 26px; border-left:1px solid var(--hair); }
.stat:first-child { padding-left:0; border-left:none; }
.stat .n { font-size:30px; font-weight:800; font-family:var(--mono); letter-spacing:-.02em; line-height:1; }
.stat .l { font-size:12.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; margin-top:6px; font-weight:600; }
.stat.fraud .n { color:var(--fraud); } .stat.legit .n { color:var(--legit); } .stat.uncertain .n { color:var(--uncertain); }
.layout { display:flex; min-height:calc(100vh - 148px); }
.rightrail { width:260px; flex-shrink:0; padding:40px 28px; border-left:1px solid var(--hair); display:none; }
@media (min-width: 1180px) { .rightrail { display:block; } }
.rail-badge {
  padding:18px; border-radius:14px; background:rgba(255,255,255,.55);
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  border:1px solid var(--glass-border); text-align:center;
}
.rail-badge img { height:46px; display:block; margin:0 auto 10px; }
.rail-badge .t { font-size:13px; font-weight:700; letter-spacing:-.01em; }
.rail-badge .d { font-size:12px; color:var(--muted); margin-top:6px; line-height:1.5; }
.rail-nav { margin-top:28px; }
.rail-nav .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--muted); font-weight:700; margin-bottom:10px; }
.rail-nav a { display:block; padding:7px 0; font-size:13px; color:var(--ink-soft); text-decoration:none; border-left:2px solid transparent; padding-left:10px; margin-left:-11px; transition:all .15s; }
.rail-nav a:hover { color:var(--accent-ink); border-left-color:var(--accent); }
.sidebar {
  width:318px; flex-shrink:0; overflow-y:auto; border-right:1px solid var(--hair);
  background:rgba(239,234,223,.5); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
}
.filters {
  display:flex; flex-wrap:wrap; gap:6px; padding:14px; border-bottom:1px solid var(--hair);
  position:sticky; top:0; z-index:2;
  background:rgba(239,234,223,.65); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
}
.filters button {
  background:transparent; border:1px solid transparent; color:var(--ink-soft); padding:6px 10px; border-radius:100px;
  cursor:pointer; font-size:12px; white-space:nowrap; font-weight:600; transition:all .15s; font-family:var(--sans);
}
.filters button:hover { background:rgba(255,255,255,.5); }
.filters button.active {
  background:rgba(255,255,255,.65); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
  border-color:var(--glass-border); color:var(--ink); font-weight:700;
  box-shadow:0 1px 2px rgba(23,21,15,.06);
}
.case-row { padding:14px 18px; border-bottom:1px solid var(--hair-soft); cursor:pointer; transition:background .12s; }
.case-row:hover { background:rgba(255,255,255,.4); }
.case-row.selected { background:rgba(255,255,255,.6); box-shadow:inset 2px 0 0 var(--accent); }
.case-row .id { font-weight:700; font-family:var(--mono); font-size:14px; }
.case-row .meta { color:var(--muted); font-size:12.5px; margin-top:5px; font-family:var(--mono); }
.pill {
  display:inline-flex; align-items:center; gap:5px; padding:2.5px 9px; border-radius:100px; font-size:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:.05em; border:1px solid transparent; font-size:12.5px;
}
.pill.fraud { background:rgba(179,38,30,.08); color:var(--fraud); border-color:rgba(179,38,30,.2); }
.pill.legitimate { background:rgba(46,107,71,.08); color:var(--legit); border-color:rgba(46,107,71,.2); }
.pill.uncertain { background:rgba(154,91,18,.08); color:var(--uncertain); border-color:rgba(154,91,18,.2); }
.route { display:inline-block; padding:2px 7px; border-radius:5px; font-size:10.5px; font-weight:800; margin-left:7px;
  font-family:var(--mono); letter-spacing:.03em; }
.route.auto { background:var(--bg3); color:var(--ink-soft); }
.route.L1 { background:rgba(154,91,18,.12); color:var(--uncertain); }
.route.L2 { background:rgba(179,38,30,.12); color:var(--fraud); }
.main { flex:1; overflow-y:auto; padding:40px 48px; max-width:920px; }
.section { padding:28px 0; border-bottom:1px solid var(--hair); }
.section:last-child { border-bottom:none; }
.section h2 {
  margin:0 0 16px 0; font-size:12.5px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); font-weight:700;
}
.case-head { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
.case-head .title { font-size:30px; font-weight:800; letter-spacing:-.02em; }
.case-head .meta-line { color:var(--muted); font-size:14px; margin-top:6px; }
.case-head .prob { font-size:46px; font-weight:800; font-family:var(--mono); letter-spacing:-.03em; text-align:right; }
.case-head .prob-label { font-size:13.5px; color:var(--muted); text-align:right; margin-top:2px; text-transform:uppercase; letter-spacing:.06em; }
.bar-bg { height:3px; background:var(--bg3); border-radius:2px; overflow:hidden; margin-top:18px; }
.bar-fill { height:100%; border-radius:2px; transition:width .3s; }
.summary-text { margin-top:20px; font-size:16.5px; line-height:1.65; color:var(--ink-soft); max-width:70ch; }
.exposure-line { margin-top:14px; font-size:14.5px; color:var(--muted); }
.exposure-line strong { color:var(--ink); font-family:var(--mono); }
.ev-item { padding:14px 0; border-bottom:1px solid var(--hair-soft); }
.ev-item:last-child { border-bottom:none; }
.ev-item .src { font-size:10.5px; color:var(--accent-ink); text-transform:uppercase; letter-spacing:.09em; font-weight:700; font-family:var(--mono); }
.ev-item .claim { margin-top:5px; line-height:1.6; font-size:15.5px; }
.action-row { display:flex; align-items:baseline; gap:8px; padding:9px 0; flex-wrap:wrap; }
.action-row .name { font-weight:700; font-size:14.5px; }
.action-row .reason { color:var(--muted); font-size:13.5px; }
.rule-tag { border-bottom:1px dotted var(--accent-ink); color:var(--accent-ink); font-weight:700; cursor:help; }
.novel-badge {
  display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:100px; font-size:11px; font-weight:800;
  text-transform:uppercase; letter-spacing:.05em; background:var(--ink); color:var(--bg); margin-left:8px;
}
.novel-badge::before { content:""; width:5px; height:5px; border-radius:50%; background:var(--accent); }
.arrow { color:var(--accent-ink); font-size:13px; padding:14px 0; font-family:var(--mono);
  text-transform:uppercase; letter-spacing:.08em; font-weight:700; border-top:1px dashed var(--hair); border-bottom:1px dashed var(--hair); margin:6px 0; }
.trace-step { display:flex; gap:14px; padding:7px 0; font-size:13px; font-family:var(--mono); align-items:baseline; }
.trace-step .t { color:var(--muted); width:56px; flex-shrink:0; }
.trace-step .kind { width:46px; flex-shrink:0; font-weight:800; font-size:10.5px; text-transform:uppercase; }
.trace-step .kind.tool { color:#2563a8; } .trace-step .kind.llm { color:var(--accent-ink); } .trace-step .kind.note { color:var(--muted); }
.simbtns { display:flex; gap:10px; margin-top:14px; }
.simbtns button {
  flex:1; padding:13px; border-radius:12px; border:1px solid var(--glass-border);
  background:rgba(255,255,255,.55); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  color:var(--ink); cursor:pointer; font-size:14px; font-weight:600; font-family:var(--sans); transition:all .15s;
}
.simbtns button:hover { background:rgba(255,255,255,.8); border-color:rgba(255,106,26,.35); box-shadow:0 2px 10px rgba(23,21,15,.06); }
.simresult {
  margin-top:16px; padding:16px 18px; border-radius:14px;
  background:rgba(255,255,255,.55); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
  border:1px solid var(--glass-border); box-shadow:0 4px 18px rgba(23,21,15,.05);
}
svg#graphview { width:100%; height:340px; background:transparent; }
.node-label { fill:var(--ink-soft); font-size:12.5px; font-family:var(--mono); }
.node-label.self { fill:var(--ink); font-weight:700; }
.empty { color:var(--muted); text-align:left; padding:24px 0; font-size:13px; }
.node-circle { cursor:pointer; transition:all .15s; }
.node-circle:hover { filter:brightness(1.15); }
.node-circle.active { stroke:var(--ink); stroke-width:1.5; }
#nodeinfo {
  margin-top:16px; padding:16px 18px; border-radius:14px;
  background:rgba(255,255,255,.6); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
  border:1px solid var(--glass-border); box-shadow:0 4px 18px rgba(23,21,15,.05); display:none;
}
#nodeinfo .close { float:right; cursor:pointer; color:var(--muted); font-size:16px; line-height:1; }
#nodeinfo .close:hover { color:var(--ink); }
.legend { display:flex; gap:20px; margin-top:14px; font-size:13.5px; color:var(--muted); flex-wrap:wrap; }
.legend .dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; }
.sar-text {
  white-space:pre-wrap; line-height:1.75; font-size:15.5px; margin-top:8px; padding:18px 20px;
  background:rgba(255,255,255,.5); border-left:2px solid var(--accent); border-radius:0 10px 10px 0;
}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>Fraud Investigation Agent</h1>
    <div class="sub">HHGOA &middot; GraphRAG &middot; GSQL + MCP + Vector Search + LLM</div>
  </div>
  <div class="savanna">
    __LOGO_IMG__
    <div class="label">Built on TigerGraph Savanna</div>
  </div>
</header>
<div class="stats" id="stats"></div>
<div class="layout">
  <div class="sidebar">
    <div class="filters" id="filters"></div>
    <div id="caselist"></div>
  </div>
  <div class="main" id="main"><div class="empty">Select a case</div></div>
  <div class="rightrail">
    <div class="rail-badge">
      __LOGO_IMG_BIG__
      <div class="t">Built on TigerGraph Savanna</div>
      <div class="d">GSQL graph queries, MCP tool calls, vector similarity search, and Groq LLM reasoning - all live against a real loaded graph.</div>
    </div>
    <div class="rail-nav" id="railnav"></div>
  </div>
</div>
<script>
const DATA = __DATA_JSON__;
const CLOSED_META = __CLOSED_META_JSON__;
let selected = null;
let filter = "all";

function verdictPill(v) { return `<span class="pill ${v}">${v}</span>`; }
function routeTag(r) { return `<span class="route ${r}">${r}</span>`; }

function renderStats() {
  const n = DATA.length;
  const fraud = DATA.filter(d => d.case.verdict === "fraud").length;
  const legit = DATA.filter(d => d.case.verdict === "legitimate").length;
  const unc = DATA.filter(d => d.case.verdict === "uncertain").length;
  const sar = DATA.filter(d => d.sar.file).length;
  const exp = DATA.reduce((s,d) => s + (d.case.exposure_usd||0), 0);
  document.getElementById("stats").innerHTML = `
    <div class="stat"><div class="n">${n}</div><div class="l">Cases Investigated</div></div>
    <div class="stat fraud"><div class="n">${fraud}</div><div class="l">Fraud Confirmed</div></div>
    <div class="stat legit"><div class="n">${legit}</div><div class="l">Legitimate</div></div>
    <div class="stat uncertain"><div class="n">${unc}</div><div class="l">Escalated</div></div>
    <div class="stat"><div class="n">${sar}</div><div class="l">SARs Filed</div></div>
    <div class="stat"><div class="n">$${exp.toFixed(2)}</div><div class="l">Exposure Actioned</div></div>`;
}

function renderFilters() {
  const opts = [["all","All"],["fraud","Fraud"],["legitimate","Legitimate"],["uncertain","Escalated"],["sar","SAR Filed"]];
  document.getElementById("filters").innerHTML = opts.map(([k,l]) =>
    `<button data-f="${k}" class="${filter===k?'active':''}">${l}</button>`).join("");
  document.querySelectorAll("#filters button").forEach(b => b.onclick = () => { filter = b.dataset.f; render(); });
}

function matchesFilter(d) {
  if (filter === "all") return true;
  if (filter === "sar") return d.sar.file;
  return d.case.verdict === filter;
}

function renderList() {
  const rows = DATA.filter(matchesFilter).map(d => `
    <div class="case-row ${selected===d.case_id?'selected':''}" data-id="${d.case_id}">
      <div class="id">${d.case_id} ${verdictPill(d.case.verdict)}${d.case.pattern === 'undocumented' ? '<span class="novel-badge">Novel Pattern</span>' : ''}</div>
      <div class="meta">${d._meta.trigger_type} &middot; p=${d.case.fraud_probability.toFixed(2)} &middot; $${d.case.exposure_usd.toFixed(2)}</div>
    </div>`).join("");
  document.getElementById("caselist").innerHTML = rows || `<div class="empty">No cases match</div>`;
  document.querySelectorAll(".case-row").forEach(r => r.onclick = () => { selected = r.dataset.id; render(); });
}

const RULES = {
  "R1": "R1: a single, uncorroborated signal below p=0.70 must be verified before any block - not blocked outright.",
  "R2": "R2: the cardholder denies a disputed transaction and at least one corroborating signal exists - block and open a case.",
  "R3": "R3: the cardholder confirms the transaction - close the case as legitimate, noting the confirmation.",
  "R4": "R4: exposure crossing a materiality threshold triggers escalation for review.",
  "R5": "R5: a card-testing sequence (small authorizations then a larger purchase) is detected - decline and require step-up authentication.",
  "R6": "R6: other cards share this transaction's device fingerprint - monitor those connected cards too.",
  "R7": "R7: a disputed charge matches the card's own recurring pattern - open a case and verify with the customer rather than block outright.",
  "R8": "R8: the verdict remains uncertain and exposure exceeds $500 - escalate to a human analyst.",
  "R9": "R9: activity matches no documented fraud typology - escalate to an analyst with a description of the pattern.",
  "R10": "R10: blocking every card on the account requires two confirmed-fraud cards or evidence of compromised credentials.",
  "3a": "Policy 3a: a case must be opened once fraud probability reaches 0.30, evidence is requested, or the transaction is disputed.",
};

function reasonHtml(reason) {
  return reason.replace(/\b(R\d{1,2}|3a)\b/g, (m) =>
    RULES[m] ? `<span class="rule-tag" title="${RULES[m].replace(/"/g,'&quot;')}">${m}</span>` : m);
}

function actionsHtml(actions) {
  return actions.map(a => `<div class="action-row"><span class="name">${a.action.replace(/_/g,' ')}</span>${routeTag(a.route)}<span class="reason">${reasonHtml(a.reason)}</span></div>`).join("");
}

const TRACE_LABELS = {
  "customer_history": "Pulled this card's transaction history",
  "gather_facts": "Computed baseline, region, device and episode facts for the flagged transaction",
  "case_memory.similar": "Searched closed-case memory for similar precedent cases",
  "simulate_reply": "Simulated the customer's response to the evidence request",
  "summary": "Wrote the case summary, grounded in the facts above",
  "sar_narrative": "Wrote the SAR narrative, grounded in the facts above",
  "assess": "Weighed the evidence against the policy's decision rules",
  "reassess": "Re-weighed the evidence after the simulated reply",
};

function renderRailNav(d) {
  const items = [
    ["sec-evidence", "Evidence"],
    ["sec-connections", "Connections"],
    ["sec-timeline", "Decision Timeline"],
  ];
  if (d.what_if) items.push(["sec-whatif", "What-If Simulator"]);
  if (d.case.pattern_description) items.push(["sec-pattern", "Undocumented Pattern"]);
  if (d.sar.file) items.push(["sec-sar", "SAR Filed"]);
  items.push(["sec-trace", "Agent Reasoning Trace"]);
  const rail = document.getElementById("railnav");
  if (!rail) return;
  rail.innerHTML = `<div class="lbl">On this case</div>` +
    items.map(([id,label]) => `<a href="#${id}">${label}</a>`).join("");
}

const NODE_COLOR = { txn:'#2e6b47', customer:'#2563a8', card:'#b3261e', case:'#9a5b12' };

function graphSVG(d) {
  const cx = 300, cy = 170;
  // base entity triangle, always present: this transaction, this card, this customer
  const base = [
    { id: d._meta.flagged_txn_id, type:'txn',      angle: -Math.PI/2, rr: 70 },
    { id: d._meta.customer_id,    type:'customer', angle:  Math.PI/2, rr: 70 },
  ];
  const cards = (d.case.connected_card_ids || []).map(c => ({id:c, type:'card'}));
  const similar = (d.case.similar_prior_cases || []).map(c => ({id:c, type:'case'}));
  const outer = [...cards, ...similar];

  const baseNodes = base.map(n => ({...n, x: cx + n.rr*Math.cos(n.angle), y: cy + n.rr*Math.sin(n.angle)}));
  const outerR = 150;
  const outerNodes = outer.map((n,i) => {
    const angle = outer.length === 1 ? 0 : (2*Math.PI*i)/outer.length;
    return {...n, x: cx + outerR*Math.cos(angle), y: cy + outerR*Math.sin(angle)};
  });
  const allNodes = [...baseNodes, ...outerNodes];

  const lines = allNodes.map(n => `<line x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" stroke="var(--hair)" stroke-width="1.5"/>`).join("");
  const dots = allNodes.map(n => `
    <g class="graphnode" data-type="${n.type}" data-id="${n.id}">
      <circle class="node-circle" cx="${n.x}" cy="${n.y}" r="10" fill="${NODE_COLOR[n.type]}" opacity="0.9"/>
      <text class="node-label" x="${n.x}" y="${n.y+22}" text-anchor="middle" style="pointer-events:none">${n.id}</text>
    </g>`).join("");
  const networkNote = outer.length
    ? `<span style="color:var(--accent)">${cards.length} connected card(s), ${similar.length} precedent case(s) found</span>`
    : `<span>No shared devices or precedent matches found - investigated in isolation</span>`;

  return `
    <svg id="graphview" viewBox="0 0 600 340">
      ${lines}
      <g class="graphnode" data-type="card_self" data-id="${d._meta.card_id}">
        <circle class="node-circle" cx="${cx}" cy="${cy}" r="15" fill="var(--accent)"/>
        <text class="node-label self" x="${cx}" y="${cy+28}" text-anchor="middle">${d._meta.card_id} (this case)</text>
      </g>
      ${dots}
    </svg>
    <div class="legend">
      <span><span class="dot" style="background:${NODE_COLOR.txn}"></span>Transaction</span>
      <span><span class="dot" style="background:${NODE_COLOR.customer}"></span>Customer</span>
      <span><span class="dot" style="background:${NODE_COLOR.card}"></span>Connected card</span>
      <span><span class="dot" style="background:${NODE_COLOR.case}"></span>Similar closed case</span>
    </div>
    <div style="margin-top:6px;font-size:13.5px;color:var(--muted)">${networkNote} &middot; click any node for details</div>
    <div id="nodeinfo"></div>`;
}

function showNodeInfo(type, id) {
  document.querySelectorAll(".node-circle").forEach(c => c.classList.remove("active"));
  const el = document.querySelector(`.graphnode[data-id="${id}"] .node-circle`);
  if (el) el.classList.add("active");
  const box = document.getElementById("nodeinfo");
  box.style.display = "block";
  const closeBtn = `<span class="close" onclick="hideNodeInfo()">&times;</span>`;

  if (type === "card_self") {
    const d = DATA.find(x => x.case_id === selected);
    box.innerHTML = `${closeBtn}<strong>Card ${id}</strong>
      <div style="color:var(--muted);font-size:13.5px;margin-top:4px">
        The card under investigation in this case. Verdict: ${d.case.verdict}, pattern: ${d.case.pattern}.
      </div>`;
  } else if (type === "txn") {
    box.innerHTML = `${closeBtn}<strong>Transaction ${id}</strong>
      <div style="color:var(--muted);font-size:13.5px;margin-top:4px">
        The flagged transaction that triggered this investigation.
      </div>`;
  } else if (type === "customer") {
    box.innerHTML = `${closeBtn}<strong>Customer ${id}</strong>
      <div style="color:var(--muted);font-size:13.5px;margin-top:4px">
        The cardholder on record for this transaction.
      </div>`;
  } else if (type === "card") {
    box.innerHTML = `${closeBtn}<strong>Card ${id}</strong>
      <div style="color:var(--muted);font-size:13.5px;margin-top:4px">
        Also used the same device fingerprint as this case's flagged transaction, within the surrounding window.
        Flagged as part of the same connected activity (R6).
      </div>`;
  } else {
    const m = CLOSED_META[id];
    if (!m) { box.innerHTML = `${closeBtn}<strong>${id}</strong>`; return; }
    box.innerHTML = `${closeBtn}<strong>Closed case ${id}</strong>
      <div style="margin-top:4px">${m.outcome === 'confirmed_fraud' ? verdictPill('fraud') : verdictPill('legitimate')}
        <span style="margin-left:8px;color:var(--muted)">pattern: ${m.pattern}</span></div>
      <div style="color:var(--muted);font-size:13.5px;margin-top:4px">
        Card ${m.card_id} &middot; exposure $${m.exposure_usd.toFixed(2)} &middot;
        retrieved as a precedent via vector similarity search over 5,565 closed cases.
      </div>`;
  }
}
function hideNodeInfo() {
  document.getElementById("nodeinfo").style.display = "none";
  document.querySelectorAll(".node-circle").forEach(c => c.classList.remove("active"));
}

function traceHtml(events) {
  if (!events.length) return `<div class="empty">No trace recorded</div>`;
  return events.map(e => {
    const label = TRACE_LABELS[e.name] || e.text || e.name || '';
    return `<div class="trace-step"><span class="t">t+${e.t}s</span><span class="kind ${e.type}">${e.type}</span><span>${label} ${e.tokens?`(${e.tokens} tok)`:''}</span></div>`;
  }).join("");
}

function simulate(d, which) {
  const branch = d.what_if[which];
  document.getElementById("simresult").innerHTML = `
    <div><strong>${which === 'confirms' ? 'If customer confirms:' : 'If customer denies:'}</strong></div>
    <div style="margin-top:6px">p = ${branch.probability.toFixed(2)} &rarr; ${verdictPill(branch.verdict)}</div>
    <div style="margin-top:6px">${actionsHtml(branch.actions)}</div>
    <div style="margin-top:6px;color:var(--muted);font-size:13.5px">${branch.explanation}</div>`;
}

function renderMain() {
  const main = document.getElementById("main");
  if (!selected) { main.innerHTML = `<div class="empty">Select a case</div>`; return; }
  const d = DATA.find(x => x.case_id === selected);
  const c = d.case;
  const barColor = c.verdict === 'fraud' ? 'var(--fraud)' : c.verdict === 'legitimate' ? 'var(--legit)' : 'var(--uncertain)';

  let html = `
    <div class="section">
      <div class="case-head">
        <div>
          <div class="title">${d.case_id} &middot; ${d._meta.customer_id} / ${d._meta.card_id}</div>
          <div style="color:var(--muted);font-size:13.5px;margin-top:4px">${d._meta.trigger_type} &middot; pattern: ${c.pattern}</div>
          ${verdictPill(c.verdict)}${c.pattern === 'undocumented' ? '<span class="novel-badge">Novel Pattern - Not in Policy</span>' : ''}
        </div>
        <div style="text-align:right"><div class="prob">${(c.fraud_probability*100).toFixed(0)}%</div><div style="color:var(--muted);font-size:12.5px">fraud probability</div></div>
      </div>
      <div class="bar-bg"><div class="bar-fill" style="width:${c.fraud_probability*100}%;background:${barColor};color:${barColor}"></div></div>
      <div class="summary-text">${c.summary}</div>
      ${c.exposure_usd > 0 ? `<div class="exposure-line">Exposure: <strong>$${c.exposure_usd.toFixed(2)}</strong></div>` : ''}
    </div>

    <div class="section" id="sec-evidence"><h2>Evidence</h2>
      ${c.evidence.map(e => `<div class="ev-item"><div class="src">${e.source}</div><div class="claim">${e.claim}</div></div>`).join("")}
    </div>

    <div class="section" id="sec-connections"><h2>Connections</h2>${graphSVG(d)}</div>

    <div class="section" id="sec-timeline"><h2>Decision Timeline</h2>
      <div><strong>Initial</strong></div>${actionsHtml(d.next_best_actions.initial)}
      ${d.evidence_requests.length ? `<div class="arrow">&darr; ${d.evidence_requests[0].type} &darr;</div>
      <div style="color:var(--muted);font-size:13.5px">${d.evidence_requests[0].assumed_response}</div>
      <div style="margin-top:8px"><strong>Final</strong></div>${actionsHtml(d.next_best_actions.final)}
      <div style="margin-top:8px;color:var(--muted);font-size:13.5px">${d.next_best_actions.what_changed}</div>` : ''}
    </div>

    ${d.what_if ? `<div class="section" id="sec-whatif"><h2>What-If Simulator</h2>
      <div style="color:var(--muted);font-size:13.5px">This case's outcome depended on a simulated reply. Try the other branch:</div>
      <div class="simbtns">
        <button onclick="simulate(DATA.find(x=>x.case_id==='${d.case_id}'),'confirms')">Customer Confirms</button>
        <button onclick="simulate(DATA.find(x=>x.case_id==='${d.case_id}'),'denies')">Customer Denies</button>
      </div>
      <div id="simresult" class="simresult" style="display:none"></div>
    </div>` : ''}

    ${c.pattern_description ? `<div class="section" id="sec-pattern"><h2>Undocumented Pattern</h2><p>${c.pattern_description}</p></div>` : ''}

    ${d.sar.file ? `<div class="section" id="sec-sar"><h2>SAR Filed</h2>
      <div style="color:var(--muted);font-size:13.5px">Reason: ${d.sar.reason}</div>
      <div class="sar-text" style="margin-top:10px">${d.sar.narrative}</div>
      <div style="margin-top:10px;color:var(--muted);font-size:13.5px">Subjects: ${d.sar.subjects.join(", ")} &middot; Total: $${d.sar.total_amount_usd} &middot; Dates: ${d.sar.activity_dates.join(" to ")}</div>
    </div>` : ''}

    <div class="section" id="sec-trace"><h2>Agent Reasoning Trace</h2>${traceHtml(d._trace)}
      <div style="margin-top:8px;color:var(--muted);font-size:13.5px">${d.tool_calls} tool calls &middot; ${d.tokens} tokens &middot; ${d.latency_s}s</div>
    </div>
  `;
  main.innerHTML = html;
  const simResultEl = document.getElementById("simresult");
  if (simResultEl) simResultEl.style.display = "none";
  document.querySelectorAll(".simbtns button").forEach(b => b.addEventListener("click", () => {
    document.getElementById("simresult").style.display = "block";
  }));
  document.querySelectorAll(".graphnode").forEach(g => g.addEventListener("click", () => {
    showNodeInfo(g.dataset.type, g.dataset.id);
  }));
  renderRailNav(d);
}

function render() { renderStats(); renderFilters(); renderList(); renderMain(); }
render();
if (DATA.length) { selected = DATA[0].case_id; render(); }
</script>
</body>
</html>"""

out = Path("ui")
out.mkdir(exist_ok=True)
logo_img = f'<img src="{LOGO_DATA_URI}" alt="TigerGraph Savanna">' if LOGO_DATA_URI else ''
logo_img_big = f'<img src="{LOGO_DATA_URI}" alt="TigerGraph Savanna">' if LOGO_DATA_URI else ''
html_final = (HTML
    .replace("__DATA_JSON__", DATA_JSON)
    .replace("__CLOSED_META_JSON__", CLOSED_META_JSON)
    .replace("__LOGO_IMG__", logo_img)
    .replace("__LOGO_IMG_BIG__", logo_img_big))
(out / "index.html").write_text(html_final, encoding="utf-8")
print(f"Wrote ui/index.html with {len(bundle)} cases embedded ({len(html_final)/1024:.0f} KB)")