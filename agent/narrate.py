"""LLM-written case summary + SAR narrative, strictly grounded in facts already computed
by detectors.py/assess.py/sar.py. Falls back to the deterministic text on any LLM failure
so the pipeline never breaks because of an API hiccup."""
import json
from .llm import complete_json

SYSTEM = (
    "You are a fraud investigation report writer for a bank. You are given FACTS that "
    "were already computed by deterministic graph queries and rules - you must not invent, "
    "guess, or add any fact, number, date, or ID that is not present in the FACTS. Your job "
    "is only to phrase the given facts clearly and professionally. If FACTS is empty or "
    "insufficient, say so plainly rather than fabricating detail."
)

SUMMARY_PROMPT = """FACTS (JSON):
{facts}

Write a 2-3 sentence case summary for a fraud analyst reading this case for the first time.
State the verdict, the pattern (if any), and the one or two strongest pieces of evidence.
Do not restate every field; pick what matters. Do not use the words "I" or "we".

Respond as JSON: {{"summary": "..."}}"""

SAR_PROMPT = """FACTS (JSON):
{facts}

Write a 6-10 sentence Suspicious Activity Report narrative using ONLY the facts given.
Cover: who (customer/card), what happened (transactions, amounts, dates), how it was
identified (evidence), and why it is being reported (the trigger for filing). Use plain,
formal, factual language - no speculation beyond what the facts state.

Respond as JSON: {{"narrative": "..."}}"""


def llm_summary(facts_dict, fallback_text):
    try:
        result, tokens = complete_json(SUMMARY_PROMPT.format(facts=json.dumps(facts_dict, default=str)),
                                       system=SYSTEM, max_tokens=200)
        return result["summary"], tokens
    except Exception:
        return fallback_text, 0


def llm_sar_narrative(facts_dict, fallback_text):
    try:
        result, tokens = complete_json(SAR_PROMPT.format(facts=json.dumps(facts_dict, default=str)),
                                       system=SYSTEM, max_tokens=500)
        return result["narrative"], tokens
    except Exception:
        return fallback_text, 0