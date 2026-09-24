"""Groq client: single entry point for the agent's LLM calls (summaries, SAR wording,
explanations). Caches by prompt hash so reruns of the 20 cases are cheap. Never used to
decide verdicts, probabilities, or actions - assess.py/actions.py own that; the LLM only
writes prose grounded in the facts it's given."""
import hashlib
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

load_dotenv(Path(__file__).parent.parent / ".env")

MODEL = "openai/gpt-oss-120b"
CACHE_DIR = Path(__file__).parent.parent / ".llm_cache"

_client = None


def get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _cache_path(prompt, model):
    h = hashlib.sha256((model + "||" + prompt).encode()).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


def complete(prompt, system="", model=MODEL, max_tokens=600, temperature=0.2, use_cache=True):
    """Returns (text, tokens_used). Retries once on rate limit."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_key = system + "\n---\n" + prompt
    path = _cache_path(cache_key, model)
    if use_cache and path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return cached["text"], cached["tokens"]

    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]

    for attempt in range(2):
        try:
            resp = get_client().chat.completions.create(
                model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
            text = resp.choices[0].message.content
            tokens = resp.usage.total_tokens
            if use_cache:
                path.write_text(json.dumps({"text": text, "tokens": tokens}), encoding="utf-8")
            return text, tokens
        except Exception as e:
            if "rate" in str(e).lower() and attempt == 0:
                time.sleep(5)
                continue
            raise


def complete_json(prompt, system="", **kwargs):
    """Same as complete(), but strips markdown fences and parses JSON. Raises on bad JSON
    so callers can fall back to their deterministic text instead of using garbage."""
    text, tokens = complete(prompt, system, **kwargs)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip()), tokens