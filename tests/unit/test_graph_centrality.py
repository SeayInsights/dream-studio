"""centrality_score must be a real measurement, not a placeholder.

core/graph/query_io.py shipped `"centrality_score": 0,  # Placeholder - can be
computed separately` while the API schema advertised a real field and the
dashboard rendered it in the dependency-graph tooltip. Every node looked equally
central. A hardcoded 0 is not a missing value — it is a wrong value presented as
a real one, which is the same failure mode as an unpriced model costing $0.00.

The subtle requirement is that centrality is a property of a node's position in
the whole graph. Computing it over a paginated page would make a node's score
depend on which page was requested, so the same node would report different
centrality on /page=1 and /page=2.
"""

from __future__ import annotations

import networkx as nx

from core.graph.query_io import _degree_centrality, graph_to_dict


def _star() -> nx.DiGraph:
    """hub connected to 4 leaves — hub is maximally central."""
    g = nx.DiGraph()
    for name in ("hub", "a", "b", "c", "d"):
        g.add_node(name, name=name, type="module", file_path=f"{name}.py")
    for leaf in ("a", "b", "c", "d"):
        g.add_edge("hub", leaf)
    return g


def test_centrality_is_not_hardcoded_zero():
    data = graph_to_dict(_star())
    scores = {n["id"]: n["centrality_score"] for n in data["nodes"]}
    assert any(
        v > 0 for v in scores.values()
    ), "every centrality_score is 0 — the placeholder is back"


def test_hub_is_more_central_than_its_leaves():
    data = graph_to_dict(_star())
    scores = {n["id"]: n["centrality_score"] for n in data["nodes"]}
    assert scores["hub"] > scores["a"], scores
    assert scores["a"] == scores["b"] == scores["c"] == scores["d"], "leaves are symmetric"


def test_hub_of_a_star_is_maximally_central():
    """hub touches all 4 others out of 4 possible — exactly 1.0."""
    assert _degree_centrality(_star())["hub"] == 1.0


def test_scores_are_normalised_between_zero_and_one():
    for node, score in _degree_centrality(_star()).items():
        assert 0.0 <= score <= 1.0, f"{node} scored {score}, outside [0, 1]"


def test_centrality_is_computed_over_the_whole_graph_not_the_page():
    """The regression that pagination invites.

    A node's centrality must be identical whether it arrives on page 1 or on a
    later page. Computing it per-page would silently rescale it.
    """
    graph = _star()
    unpaginated = {n["id"]: n["centrality_score"] for n in graph_to_dict(graph)["nodes"]}

    seen: dict[str, float] = {}
    for offset in range(0, graph.number_of_nodes(), 2):
        page = graph_to_dict(graph, limit=2, offset=offset)
        for node in page["nodes"]:
            seen[node["id"]] = node["centrality_score"]

    assert seen == unpaginated, (
        "centrality changed under pagination — it must be computed over the "
        f"full graph. paged={seen} full={unpaginated}"
    )


def test_isolated_node_scores_zero():
    g = nx.DiGraph()
    g.add_node("lonely", name="lonely", type="module")
    g.add_node("other", name="other", type="module")
    assert _degree_centrality(g)["lonely"] == 0.0


def test_degenerate_graphs_do_not_raise():
    """n < 2 has no meaningful normaliser — must not divide by zero."""
    empty = nx.DiGraph()
    assert _degree_centrality(empty) == {}

    single = nx.DiGraph()
    single.add_node("only", name="only", type="module")
    assert _degree_centrality(single) == {"only": 0.0}
    # And through the public path.
    assert graph_to_dict(single)["nodes"][0]["centrality_score"] == 0.0
