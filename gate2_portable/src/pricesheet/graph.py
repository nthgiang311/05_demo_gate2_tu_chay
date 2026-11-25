"""LangGraph wrapper (spec 2.6): one StateGraph, one node `normalize`, compiled once, no checkpointer.
CLI, API and review page all call `normalize()`."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .mapping_rules import RULES_V2
from .override import apply_override, enrich
from .pipeline import run


class State(TypedDict, total=False):
    path: str
    mode: str
    use_llm: bool
    use_cache: bool
    override: Any
    lenient_rows: Any   # internal (review sessions), never from user input
    rules: str          # "v1" (default) or "v2"
    result: dict


def _normalize(s: State) -> dict:
    mode = s.get("mode") or "rule_first"
    token = RULES_V2.set(s.get("rules") == "v2")
    try:
        if s.get("override") is not None:  # override run: rules only, 0 model calls
            res = apply_override(s["path"], s["override"], mode, s.get("lenient_rows", ()))
        else:
            res = enrich(run(s["path"], mode, s.get("use_llm", True), s.get("use_cache", True)), s["path"])
    finally:
        RULES_V2.reset(token)
    res["rules"] = s.get("rules") or "v1"
    return {"result": res}


_g = StateGraph(State)
_g.add_node("normalize", _normalize)
_g.add_edge(START, "normalize")
_g.add_edge("normalize", END)
GRAPH = _g.compile()


def normalize(path, mode="rule_first", use_llm=True, use_cache=True, override=None, lenient_rows=(), rules="v1"):
    state = {"path": path, "mode": mode, "use_llm": use_llm, "use_cache": use_cache, "override": override,
             "lenient_rows": list(lenient_rows), "rules": rules}
    return GRAPH.invoke(state)["result"]
