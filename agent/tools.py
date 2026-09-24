"""MCP client wrapper: lets the synchronous agent pipeline (detectors/assess/actions)
call TigerGraph through the tigergraph-mcp server instead of hand-run Query Editor calls.

Each public function here opens a fresh MCP session, calls one tool, and returns plain
Python data (dict/list), so the rest of the agent never has to know MCP exists.
"""
import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
PREFIX = "tigergraph__"


def _parse_result(result):
    """MCP tool results come back as a list of content blocks; TigerGraph-MCP's tools
    return their payload as a JSON string in the first TextContent block, wrapped in an
    envelope like {"success": bool, "data": {...}, "error": ...}. We unwrap it here so
    callers get plain data (or raise on failure) instead of re-parsing the envelope
    every time."""
    if not result.content:
        return None
    text = result.content[0].text
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    if isinstance(parsed, dict) and "success" in parsed:
        if not parsed["success"]:
            raise RuntimeError(f"MCP tool failed: {parsed.get('error', parsed.get('summary'))}")
        data = parsed.get("data", parsed)
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data
    return parsed


async def _call(tool_name, arguments):
    params = StdioServerParameters(command="tigergraph-mcp", args=["--env-file", ENV_FILE])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(PREFIX + tool_name, arguments)
            return _parse_result(result)


def call_tool(tool_name, **arguments):
    """Synchronous entry point - run any TigerGraph MCP tool by its short name
    (without the 'tigergraph__' prefix, which is added automatically)."""
    return asyncio.run(_call(tool_name, arguments))


# ------------------------------------------------------------------ our 4 GSQL queries
def run_installed_query(query_name, params):
    return call_tool("run_installed_query", query_name=query_name, params=params)


def card_baseline(card_id, cutoff):
    """Mirrors detectors.baseline(): txn count/amount stats for a card before cutoff.
    Returns a single dict, e.g. {"txn_count": 2252, "total_amt": 276548.89, ...}."""
    r = run_installed_query("card_baseline", {"card_id": card_id, "cutoff": cutoff})
    return r[0] if isinstance(r, list) else r


def region_routine(card_id, region_id, cutoff):
    """Mirrors detectors.region_stats(): how established is this billing region for this card."""
    r = run_installed_query("region_routine",
                            {"card_id": card_id, "region_id": str(region_id), "cutoff": cutoff})
    return r[0] if isinstance(r, list) else r


def card_testing_check(card_id, center_ts, lookaround_hours=24):
    """Mirrors detectors.card_testing(): tiny online-txn burst candidates near center_ts."""
    r = run_installed_query("card_testing_check",
                            {"card_id": card_id, "center_ts": center_ts,
                             "lookaround_hours": lookaround_hours})
    return r[0] if isinstance(r, list) else r


def shared_device_ring(device_id, exclude_card, center_ts, window_days=30):
    """Mirrors detectors.shared_device(): other cards using the same device profile.
    Returns (stats_dict, list_of_card_vertex_dicts)."""
    r = run_installed_query("shared_device_ring",
                            {"device_id": device_id, "exclude_card": exclude_card,
                             "center_ts": center_ts, "window_days": window_days})
    stats = r[0] if len(r) > 0 else {}
    cards = r[1].get("Cards", []) if len(r) > 1 else []
    return stats, cards


# ------------------------------------------------------------------ vector / GraphRAG
def search_similar_cases(query_vector, vertex_type="ClosedCase", vector_attr="embedding", k=5):
    """Top-k closed cases by embedding similarity (COSINE). Returns TigerGraph's raw
    result list; each item typically has {"v_id": "CC-####", "distance": float, ...}."""
    return call_tool("search_top_k_similarity", vertex_type=vertex_type,
                      vector_attribute=vector_attr, query_vector=query_vector, top_k=k)


# ------------------------------------------------------------------ write FraudCase back
def write_fraud_case(case_id, attributes):
    return call_tool("add_node", vertex_type="FraudCase", vertex_id=case_id, attributes=attributes)


def link_case(case_id, edge_type, target_type, target_id, attributes=None):
    return call_tool("add_edge", source_vertex_type="FraudCase", source_vertex_id=case_id,
                      edge_type=edge_type, target_vertex_type=target_type,
                      target_vertex_id=target_id, attributes=attributes or {})


if __name__ == "__main__":
    print("card_baseline:", card_baseline("C09933", "2016-11-22 00:00:00"))
    print("region_routine:", region_routine("C09933", "264.0", "2016-11-22 00:00:00"))