from intelgraph.core.entity import Person
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _make_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    carol = Person(name="Carol")
    dave = Person(name="Dave")
    g.add_entity(alice)
    g.add_entity(bob)
    g.add_entity(carol)
    g.add_entity(dave)
    r1 = Relationship(
        source_id=alice.id,
        target_id=bob.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    r2 = Relationship(
        source_id=bob.id,
        target_id=carol.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    r3 = Relationship(
        source_id=bob.id,
        target_id=dave.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    g.add_relationship(r1)
    g.add_relationship(r2)
    g.add_relationship(r3)
    return g


class TestGraphDataModel:
    def test_add_entity(self):
        g = IntelligenceGraph()
        p = Person(name="Test")
        n = g.add_entity(p)
        assert n.id == p.id
        assert g.has_node(p.id)
        assert g.node_count == 1
        assert p.id in g.adjacency
        assert p.id in g.forward_adjacency
        assert p.id in g.reverse_adjacency
        assert p.id in g.node_edges

    def test_add_relationship(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        r = Relationship(
            source_id=a.id,
            target_id=b.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        e = g.add_relationship(r)
        assert e.id == r.id
        assert g.edge_count == 1
        assert b.id in g.forward_adjacency[a.id]
        assert a.id in g.reverse_adjacency[b.id]
        assert b.id in g.adjacency[a.id]
        assert a.id in g.adjacency[b.id]
        assert e.id in g.edge_node_map
        assert e.id in g.node_edges[a.id]
        assert e.id in g.node_edges[b.id]

    def test_get_node_and_edge(self):
        g = _make_graph()
        all_nodes = list(g.nodes.values())
        assert g.get_node(all_nodes[0].id) is all_nodes[0]
        assert g.get_node("nonexistent") is None
        all_edges = list(g.edges.values())
        assert g.get_edge(all_edges[0].id) is all_edges[0]
        assert g.get_edge("nonexistent") is None

    def test_remove_edge(self):
        g = _make_graph()
        edges_before = g.edge_count
        eid = next(iter(g.edges))
        assert g.remove_edge(eid)
        assert eid not in g.edges
        assert g.edge_count == edges_before - 1
        assert not g.remove_edge("nonexistent")

    def test_remove_node(self):
        g = _make_graph()
        alice = next(iter(g.nodes.values()))
        nid = alice.id
        assert g.remove_node(nid)
        assert nid not in g.nodes
        assert not g.remove_node(nid)

    def test_remove_node_cleans_edges(self):
        g = _make_graph()
        nid = next(iter(g.nodes))
        before = g.edge_count
        g.remove_node(nid)
        assert g.edge_count < before


class TestNodeEdgeIndex:
    def test_edges_for_node(self):
        g = _make_graph()
        bob_id = None
        for n in g.nodes.values():
            if n.entity.name == "Bob":
                bob_id = n.id
                break
        edges = list(g.edges_for_node(bob_id))
        assert len(edges) == 3
        outgoing = list(g.edges_for_node(bob_id, direction="outgoing"))
        assert len(outgoing) == 2
        incoming = list(g.edges_for_node(bob_id, direction="incoming"))
        assert len(incoming) == 1

    def test_edges_for_node_isolated(self):
        g = IntelligenceGraph()
        p = Person(name="Isolated")
        g.add_entity(p)
        assert list(g.edges_for_node(p.id)) == []

    def test_nodes_for_edge(self):
        g = _make_graph()
        eid = next(iter(g.edges))
        nodes = g.nodes_for_edge(eid)
        assert nodes is not None
        assert len(nodes) == 2
        assert isinstance(nodes[0].entity, Person)
        assert isinstance(nodes[1].entity, Person)

    def test_nodes_for_edge_missing(self):
        g = _make_graph()
        assert g.nodes_for_edge("nonexistent") is None


class TestBFS:
    def test_bfs_basic(self):
        g = _make_graph()
        alice_id = None
        for n in g.nodes.values():
            if n.entity.name == "Alice":
                alice_id = n.id
                break
        result = g.bfs(alice_id)
        assert len(result) == 4
        names = [n.entity.name for n in result]
        assert names[0] == "Alice"
        assert names[1] == "Bob"

    def test_bfs_isolated(self):
        g = IntelligenceGraph()
        p = Person(name="Alone")
        g.add_entity(p)
        result = g.bfs(p.id)
        assert len(result) == 1
        assert result[0].entity.name == "Alone"

    def test_bfs_nonexistent(self):
        g = _make_graph()
        assert g.bfs("nonexistent") == []


class TestDFS:
    def test_dfs_basic(self):
        g = _make_graph()
        alice_id = None
        for n in g.nodes.values():
            if n.entity.name == "Alice":
                alice_id = n.id
                break
        result = g.dfs(alice_id)
        assert len(result) == 4

    def test_dfs_isolated(self):
        g = IntelligenceGraph()
        p = Person(name="Alone")
        g.add_entity(p)
        result = g.dfs(p.id)
        assert len(result) == 1

    def test_dfs_nonexistent(self):
        assert IntelligenceGraph().dfs("x") == []


class TestShortestPath:
    def test_shortest_path_direct(self):
        g = _make_graph()
        ids = {n.entity.name: n.id for n in g.nodes.values()}
        path = g.shortest_path(ids["Alice"], ids["Bob"])
        assert len(path) == 2
        assert path[0].entity.name == "Alice"
        assert path[1].entity.name == "Bob"

    def test_shortest_path_multi_hop(self):
        g = _make_graph()
        ids = {n.entity.name: n.id for n in g.nodes.values()}
        path = g.shortest_path(ids["Alice"], ids["Carol"])
        assert len(path) == 3
        assert [n.entity.name for n in path] == ["Alice", "Bob", "Carol"]

    def test_shortest_path_same_node(self):
        g = _make_graph()
        alice_id = next(iter(g.nodes))
        path = g.shortest_path(alice_id, alice_id)
        assert len(path) == 1

    def test_shortest_path_unreachable(self):
        g = _make_graph()
        isolated = Person(name="Isolated")
        g.add_entity(isolated)
        alice_id = None
        for n in g.nodes.values():
            if n.entity.name == "Alice":
                alice_id = n.id
                break
        path = g.shortest_path(alice_id, isolated.id)
        assert path == []

    def test_shortest_path_nonexistent(self):
        g = _make_graph()
        alice_id = next(iter(g.nodes))
        assert g.shortest_path(alice_id, "nope") == []
        assert g.shortest_path("nope", alice_id) == []


class TestBFSDepth:
    def test_depth_0(self):
        g = _make_graph()
        alice_id = next((n.id for n in g.nodes.values() if n.entity.name == "Alice"), None)
        result = g.bfs_depth(alice_id, 0)
        assert len(result) == 1

    def test_depth_1(self):
        g = _make_graph()
        alice_id = next((n.id for n in g.nodes.values() if n.entity.name == "Alice"), None)
        result = g.bfs_depth(alice_id, 1)
        assert len(result) == 2

    def test_depth_negative(self):
        g = _make_graph()
        alice_id = next(iter(g.nodes))
        assert g.bfs_depth(alice_id, -1) == []


class TestSubgraph:
    def test_extract_subgraph_depth_1(self):
        g = _make_graph()
        alice_id = next((n.id for n in g.nodes.values() if n.entity.name == "Alice"), None)
        sub = g.extract_subgraph(alice_id, max_depth=1)
        assert sub.node_count == 2
        assert sub.edge_count == 1
        names = {n.entity.name for n in sub.nodes.values()}
        assert names == {"Alice", "Bob"}

    def test_extract_subgraph_depth_2(self):
        g = _make_graph()
        alice_id = next((n.id for n in g.nodes.values() if n.entity.name == "Alice"), None)
        sub = g.extract_subgraph(alice_id, max_depth=2)
        assert sub.node_count == 4
        assert sub.edge_count == 3

    def test_subgraph_isolation(self):
        g = _make_graph()
        alice_id = next((n.id for n in g.nodes.values() if n.entity.name == "Alice"), None)
        sub = g.extract_subgraph(alice_id, max_depth=1)
        sub.add_entity(Person(name="New"))
        assert g.node_count == 4
        assert g.has_node("New") is False

    def test_extract_subgraph_disconnected(self):
        g = _make_graph()
        isolated = Person(name="Isolated")
        g.add_entity(isolated)
        sub = g.extract_subgraph(isolated.id, max_depth=2)
        assert sub.node_count == 1
        assert sub.edge_count == 0
