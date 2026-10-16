"""Compile the declarative ``GraphSpec`` into a LangGraph state machine."""
from __future__ import annotations

from typing import Any

from app.agents.graph_spec import END, GraphSpec
from app.agents.state import ConciergeState


def compile_graph(spec: GraphSpec, checkpointer: Any):
    """Build and compile the LangGraph ``StateGraph`` for the concierge.

    Args:
        spec: Nodes, edges and routers from ``build_spec``.
        checkpointer: A LangGraph checkpoint saver (Postgres or in-memory).
    """
    from langgraph.graph import END as LG_END
    from langgraph.graph import START, StateGraph

    graph = StateGraph(ConciergeState)
    for name, fn in spec.nodes.items():
        graph.add_node(name, fn)
    graph.add_edge(START, spec.entry)
    for source, target in spec.edges.items():
        graph.add_edge(source, LG_END if target == END else target)
    for source, (router, mapping) in spec.conditional.items():
        graph.add_conditional_edges(source, router, mapping)
    return graph.compile(checkpointer=checkpointer)
