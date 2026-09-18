"""
Self-check for two fixed defects. Run: python test_fixes.py

1. final_formatter_node must emit column-zero, parseable YAML frontmatter
   (it used to be indented by the f-string and broke on a colon in the title).
2. try_stream must execute the graph exactly once
   (it used to stream and then invoke(), running everything twice).
"""
import operator
from typing import TypedDict, Annotated, List

import yaml
from langgraph.graph import StateGraph, START, END

from bwa_backend import SEOAudit, final_formatter_node


def test_frontmatter_parses():
    # A colon in the title and a quote in the description are the cases that
    # broke the old f-string version.
    audit = SEOAudit(
        seo_title='Agentic AI: A Developer"s Guide',
        meta_description="Why it matters: cost, latency & grounding",
        slug="agentic-ai-guide",
        estimated_reading_time=7,
        seo_score=82,
        strengths=[],
        improvements=[],
        faq_section="## FAQ\n\n**Q?** A.",
    )
    out = final_formatter_node({"seo_audit": audit, "final": "# Title\n\nBody."})["final"]

    assert out.startswith("---\n"), "frontmatter must open at column zero"
    _, raw, body = out.split("---\n", 2)

    for line in raw.splitlines():
        assert line == line.lstrip(), f"indented frontmatter line: {line!r}"

    meta = yaml.safe_load(raw)
    assert meta["title"] == audit.seo_title, meta["title"]
    assert meta["description"] == audit.meta_description
    assert meta["seo_score"] == 82 and meta["reading_time"] == 7
    assert "# Title" in body and audit.faq_section in body
    print("ok  frontmatter parses as YAML and round-trips a colon in the title")


def test_graph_runs_once():
    calls = {"n": 0}

    class S(TypedDict):
        final: str
        sections: Annotated[List[int], operator.add]

    def a(_s):
        calls["n"] += 1
        return {"final": "draft", "sections": [1]}

    def b(_s):
        return {"final": "done", "sections": [2]}

    g = StateGraph(S)
    g.add_node("a", a)
    g.add_node("b", b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    app = g.compile()

    from bwa_frontend import try_stream

    nodes, finals = [], []
    for kind, payload in try_stream(app, {"final": "", "sections": []}):
        if kind == "updates":
            nodes.extend(payload.keys())
        elif kind == "final":
            finals.append(payload)

    assert calls["n"] == 1, f"graph executed {calls['n']}x, expected 1"
    assert nodes == ["a", "b"], nodes
    assert len(finals) == 1, f"expected one final, got {len(finals)}"
    # reducer applied -> proves this is real final state, not an updates delta
    assert finals[0]["final"] == "done"
    assert finals[0]["sections"] == [1, 2], finals[0]["sections"]
    print("ok  graph executed once, progress yielded, final state complete")


if __name__ == "__main__":
    test_frontmatter_parses()
    test_graph_runs_once()
    print("\nall checks passed")
