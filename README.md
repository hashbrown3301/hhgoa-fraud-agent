# Fraud Investigation Agent — HHGOA (TigerGraph x Hacker House Goa)

An agentic fraud investigation system built on **TigerGraph Savanna**. Given an alert
(a risk-score flag, a customer report, or an analyst request), the agent gathers evidence
through real GSQL graph queries and a TigerGraph vector store, weighs that evidence against
a written bank policy, recommends next-best actions with the correct approval route, asks
for more evidence when it's genuinely uncertain, and writes the finished case back into the
graph. Investigates all 20 benchmark cases (`HHG-001` – `HHG-020`) end to end.

**[Demo video](#)** · **[Blog post](#)** · Dataset: IEEE-CIS Fraud Detection (via the HHGOA
benchmark pack)

---

## What's actually in here

| Requirement | How we met it |
|---|---|
| TigerGraph for storage & retrieval | Full schema loaded on Savanna: Customer, Card, Txn, DeviceProfile, Region, ClosedCase, FraudCase — real data, not a demo graph |
| GSQL + graph algorithms | 4 custom GSQL queries (`card_baseline`, `region_routine`, `card_testing_check`, `shared_device_ring`) plus TigerGraph's built-in **Weakly Connected Components** algorithm, run and honestly interpreted (see [Blog post](#)) |
| TigerGraph MCP | `agent/tools.py` — the agent calls the graph exclusively through MCP, not a raw driver |
| GraphRAG | 5,565 closed-case notes embedded (`sentence-transformers`, local/free) and loaded into a TigerGraph vector attribute; retrieval via `search_top_k_similarity`, verified to surface the correct precedent cases |
| LLM reasoning | Groq (`openai/gpt-oss-120b`) writes case summaries and SAR narratives, strictly grounded in facts computed upstream — never used to decide verdicts or actions |
| Case memory | `ClosedCase` vertices + vector index; each investigated case is also written back as a `FraudCase` vertex, linked to its customer, card, transactions, and cited precedents |
| UI | Self-contained `ui/index.html` — case explorer, evidence, interactive connections graph, decision timeline, what-if simulator, agent reasoning trace |

---

## Architecture

```
Alert (case_pack.csv)
   │
   ▼
detectors.py ──────► gather_facts()        deterministic facts: baseline, region history,
   │                                        card-testing check, device signals, episode
   │                                        (via GSQL queries + MCP, agent/tools.py)
   ▼
assess.py ──────────► assess()             evidence-counting decision table (no fitted
   │                                        weights) → probability, verdict, pattern
   │                                        + memory.py / TigerGraph vector search for
   │                                          precedent closed cases
   ▼
actions.py ─────────► plan_case()          policy.py-derived next-best actions, routes
   │                                        (auto/L1/L2), and — if uncertain — a simulated
   │                                        evidence request + reassessment
   ▼
sar.py + narrate.py ─► SAR + summary        deterministic SAR skeleton, wording finished by
   │                                        Groq (agent/llm.py), grounded in the same facts
   ▼
schema.py ──────────► validate()           checks the answer against the required format —
   │                                        wrong routes, missing SAR fields, mismatched
   │                                        exposure, etc. all caught before it's written
   ▼
cases/HHG-*.json  +  write-back to TigerGraph (FraudCase vertices + edges)
   │
   ▼
build_ui.py ────────► ui/index.html        bundles the 20 cases + trace logs into one
                                            offline-ready dashboard
```

---

## Repo layout

```
agent/
  policy.py        Bank fraud policy as code: actions, approval routes, R1–R10, stop rule
  schema.py         Answer-file builder + validator (the strictest gate before submission)
  detectors.py      Deterministic facts: baseline, region/routine, card-testing, device ring
  memory.py         Closed-case retrieval (local TF-IDF prototype; see note below)
  features.py / model.py   Calibration experiment on the closed-case history — kept as an
                    honest ablation (see "What we tried and rejected")
  assess.py         Evidence-counting decision table → probability / verdict / pattern
  actions.py        Turns an assessment into policy-compliant next-best actions
  sar.py            Deterministic SAR skeleton (who/what/when/how/why)
  tools.py          TigerGraph MCP client wrapper — every graph call goes through here
  embeddings.py     Local sentence-transformers embeddings for GraphRAG
  llm.py / narrate.py   Groq client + grounded summary/SAR-narrative prompts
  tracer.py         Records tool_calls / tokens / latency_s per case

graph/queries/      GSQL source for the 4 custom queries (also installed live on Savanna)
data/               case_pack.csv, closed_cases_history.csv (raw data NOT committed — see below)
cases/              The 20 answer files: HHG-001.json – HHG-020.json
logs/               Per-case reasoning trace (tool_calls/llm calls with timestamps)
ui/index.html        Self-contained dashboard (open directly in a browser, no server)
assets/savanna-logo.png   Embedded into the UI header at build time

build_answer.py      Runs the full pipeline for all 20 cases → cases/*.json
build_features.py    Full-dataset feature pass (used only for the rejected ML experiment)
build_case_vectors.py  Embeds all 5,565 closed cases for the TigerGraph vector store
build_ui.py           Bundles everything into ui/index.html
write_back.py         Writes each finished case into TigerGraph as a FraudCase vertex
add_whatif_branches.py  Precomputes both reply branches for the UI's what-if simulator
prepare_graph_csvs.py / gen_ring_supplement.py   One-time graph-loading helpers
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Get the dataset**
Place the HHGOA benchmark files in `data/`: `case_pack.csv`, `closed_cases_history.csv`,
`identity.csv`, `transactions.csv`. The raw transaction file is ~700MB and is not committed;
see the challenge's own dataset instructions for where to get it.

**3. TigerGraph Savanna**
- Create a free workspace at [savanna.tgcloud.io](https://savanna.tgcloud.io)
- Enable **Auto Suspend** and **Auto Resume** in workspace settings
- Create a **Database Secret** (Database Secrets → Create Secret) for MCP auth
- Run the schema (see `graph/queries/` and the setup steps in the blog post) to create
  `FraudGraph` with the Customer/Card/Txn/DeviceProfile/Region/ClosedCase/FraudCase vertices

**4. Environment variables**
```bash
cp .env.example .env
# fill in TG_HOST, TG_SECRET, GROQ_API_KEY
```

**5. Run the pipeline**
```bash
python build_features.py          # optional: closed-case feature pass (calibration experiment)
python build_case_vectors.py      # embed closed cases locally
# → load embeddings into TigerGraph's vector store (see blog post for the MCP calls)
python build_answer.py            # produces cases/HHG-001.json … HHG-020.json
python write_back.py              # writes each case into TigerGraph as a FraudCase vertex
python add_whatif_branches.py     # precomputes both reply branches for the UI
python build_ui.py                # produces ui/index.html
```

**6. View the result**
Open `ui/index.html` directly in a browser. No server required.

**7. Run the tests**
```bash
python -m pytest -q tests
```

---

## Design decisions worth knowing about

- **Probability is a decision table, not a fitted model.** We tried training a logistic
  regression on the 5,565 closed cases (98.5% AUC). Backtesting it against hand-verified
  cases showed it had learned "high risk score → cleared" — backwards for exactly the cases
  that matter. We rejected it and kept the transparent, rule-based evidence counter in
  `assess.py`. Full story in the blog post.
- **Weakly Connected Components was run and honestly reported, not massaged.** TigerGraph's
  built-in `tg_wcc` collapses our device-sharing graph into one dominant "small-world"
  component (~28,858 of ~28,861 vertices) — a known, documented phenomenon for
  device-fingerprint graphs, which is why TigerGraph ships a small-world-optimized WCC
  variant. We used this finding to justify why our targeted, single-device-profile ring
  detector (`shared_device_ring`) is the right tool for this data, rather than quietly
  discarding an inconvenient result.
- **`Card.id == customer_id`.** `transactions.csv` has no per-transaction card identifier —
  each customer maps to one card in this data — so the graph models Card 1:1 with Customer
  for simplicity. Noted explicitly so it isn't mistaken for an oversight.
- **The LLM never decides anything.** Verdicts, probabilities, routes, and actions are all
  deterministic, policy-derived code (`policy.py`, `assess.py`, `actions.py`). Groq is used
  only to phrase already-computed facts into readable prose for `case.summary` and the SAR
  narrative — with a deterministic fallback if the API call ever fails.

---

## Judging-criteria self-check

| Criterion | Where to look |
|---|---|
| Investigation accuracy | `cases/*.json` → `case.evidence`, `case.pattern`; `agent/assess.py` for the decision logic |
| Next best action | `cases/*.json` → `next_best_actions`; `agent/policy.py` for the exact rule text |
| Explainability | `ui/index.html` — evidence, decision timeline, rule-citation tooltips, reasoning trace |
| Agentic design | `agent/tools.py` (MCP), `graph/queries/` (GSQL), `agent/memory.py` + vector store (GraphRAG) |
| Innovation | `HHG-014` — an undocumented device-ring pattern (R9), flagged distinctly in the UI |
| Demo | [link](#) |

---

## Team / Attribution

Built for the TigerGraph x Hacker House Goa hackathon. Dataset: IEEE-CIS Fraud Detection
(Vesta Corporation), adapted for the HHGOA benchmark. Powered by TigerGraph Savanna.