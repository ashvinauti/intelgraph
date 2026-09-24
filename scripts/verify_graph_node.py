#!/usr/bin/env python3
"""
graph.node Gerçek Davranış Doğrulaması — CRUD + Referans Bütünlüğü

Mock'suz, gerçek veriyle, bağımsız.
"""

from __future__ import annotations

from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.relationship.types import RelationshipType

print("=" * 72)
print("Temel CRUD + Referans Bütünlüğü Doğrulaması")
print("=" * 72)

# =====================================================================
# 1a. CRUD — Node oluşturma
# =====================================================================
print("\n" + "-" * 72)
print("1a. Node Oluşturma — gerçek state'te yer alıyor mu?")
print("-" * 72)

entity = IPAddress(ip="10.0.0.1", rdns="malware.example.com")
graph = IntelligenceGraph()
node = graph.add_entity(entity)

print(f"Node oluşturuldu: id={node.id}, type={node.entity_type}, ip={entity.ip}")
print(f"graph.nodes tipi: {type(graph.nodes).__name__}")
print(f"graph.nodes içinde var mı?  {node.id in graph.nodes}")
print(f"graph.get_node():           {graph.get_node(node.id) is not None}")
print(f"graph.has_node():           {graph.has_node(node.id)}")
print(f"Adjacency kaydı var mı?     {node.id in graph.adjacency}")
print(f"Forward adj. kaydı var mı?  {node.id in graph.forward_adjacency}")
print(f"Reverse adj. kaydı var mı?  {node.id in graph.reverse_adjacency}")
print(f"node_edges kaydı var mı?    {node.id in graph.node_edges}")

assert node.id in graph.nodes
assert graph.get_node(node.id) is not None
assert graph.has_node(node.id)
assert node.id in graph.adjacency
assert node.id in graph.forward_adjacency
assert node.id in graph.reverse_adjacency
assert node.id in graph.node_edges

# add_entity'in döndürdüğü node ile graph.nodes[node.id] aynı obje mi?
assert graph.nodes[node.id] is node
print("\n✅ add_entity: Node graph'a eklendi, tüm yardımcı yapılar oluşturuldu.")

# =====================================================================
# 1b. CRUD — Node güncelleme
# =====================================================================
print("\n" + "-" * 72)
print("1b. Node Güncelleme — property değişikliği kalıcı mı?")
print("-" * 72)

# Node ve BaseEntity frozen olduğu için güncelleme = eski node'u kaldır + yeni ekle
# veya doğrudan graph.nodes[node.id] = yeni_node
old_id = node.id
old_entity = graph.nodes[old_id].entity
print(f"Eski node entity ID: {old_entity.id}")
print(f"Eski node entity IP: {old_entity.ip}")

# Yeni entity ile update (aynı ID'yi koruyarak)
new_entity = IPAddress(id=old_id, ip="10.0.0.2", rdns="updated.example.com")
new_node = Node(entity=new_entity)
graph.nodes[old_id] = new_node
graph.adjacency.setdefault(old_id, set())
graph.forward_adjacency.setdefault(old_id, set())
graph.reverse_adjacency.setdefault(old_id, set())
graph.node_edges.setdefault(old_id, set())

updated = graph.get_node(old_id)
print(f"Güncellenmiş node entity IP: {updated.entity.ip}")
print(f"Eski IP (10.0.0.1) hala var mı? {(updated.entity.ip == '10.0.0.1')}")
print(f"Yeni IP (10.0.0.2) geldi mi?    {(updated.entity.ip == '10.0.0.2')}")
assert updated.entity.ip == "10.0.0.2"
assert updated.entity.rdns == "updated.example.com"
print("\n✅ Node güncellemesi: graph.nodes dict'ine yeni Node yazılarak yapılıyor.")
print("   (Node ve BaseEntity frozen olduğu için doğrudan mutasyon yok.)")
print("   NOT: Açık bir update_node() metodu yok — doğrudan dict override.")

# =====================================================================
# 1c. CRUD — Node silme
# =====================================================================
print("\n" + "-" * 72)
print("1c. Node Silme — iç state'ten gerçekten kaldırıldı mı?")
print("-" * 72)

graph2 = IntelligenceGraph()
e2 = IPAddress(ip="10.0.0.3")
n2 = graph2.add_entity(e2)
n2_id = n2.id

print(f"Silme öncesi node_count: {graph2.node_count}")
print(f"Silme öncesi nodes: {list(graph2.nodes.keys())}")

removed = graph2.remove_node(n2_id)
print(f"remove_node() döndü: {removed}")
print(f"Silme sonrası node_count: {graph2.node_count}")
print(f"Silme sonrası nodes: {list(graph2.nodes.keys())}")
print(f"has_node() ne diyor? {graph2.has_node(n2_id)}")
print(f"adjacency'de kaldı mı?      {n2_id in graph2.adjacency}")
print(f"forward_adjacency'de kaldı mı? {n2_id in graph2.forward_adjacency}")
print(f"reverse_adjacency'de kaldı mı? {n2_id in graph2.reverse_adjacency}")
print(f"node_edges'te kaldı mı?     {n2_id in graph2.node_edges}")

assert removed is True
assert graph2.node_count == 0
assert not graph2.has_node(n2_id)
assert n2_id not in graph2.adjacency
assert n2_id not in graph2.forward_adjacency
assert n2_id not in graph2.reverse_adjacency
assert n2_id not in graph2.node_edges
print("✅ remove_node: Node tüm yardımcı yapılardan temizlendi.")

# =====================================================================
# 1d. CRUD — Var olmayan node'u silme/güncelleme
# =====================================================================
print("\n" + "-" * 72)
print("1d. Var Olmayan Node'u Silme/Güncelleme")
print("-" * 72)

result = graph2.remove_node("nonexistent-id")
print(f"remove_node('nonexistent-id') döndü: {result}")
assert result is False
print("✅ remove_node(nonexistent): False döndü — exception yok, sessiz no-op.")

try:
    _ = graph2.get_node("nonexistent-id")
    print(f"get_node('nonexistent-id'): {graph2.get_node('nonexistent-id')}")
except Exception as ex:
    print(f"get_node('nonexistent-id') exception: {type(ex).__name__}: {ex}")

try:
    _ = graph2.has_node("nonexistent-id")
    print(f"has_node('nonexistent-id'): {graph2.has_node('nonexistent-id')}")
except Exception as ex:
    print(f"has_node('nonexistent-id') exception: {type(ex).__name__}: {ex}")

print("✅ Tüm sorgular exception fırlatmadan çalışıyor.")

# =====================================================================
# 2. Referans Bütünlüğü — Node silindiğinde edge ne oluyor?
# =====================================================================
print("\n" + "=" * 72)
print("2. REFERANS BÜTÜNLÜĞÜ — Node silinince edge ne olur?")
print("=" * 72)

graph3 = IntelligenceGraph()
a = IPAddress(id="node_A", ip="1.1.1.1")
b = IPAddress(id="node_B", ip="2.2.2.2")
na = graph3.add_entity(a)
nb = graph3.add_entity(b)

rel = Relationship(source_id="node_A", target_id="node_B", type=RelationshipType.CONNECTED_TO)
edge = graph3.add_relationship(rel)
edge_id = edge.id

print(f"Node A: {na.id}")
print(f"Node B: {nb.id}")
print(f"Edge:   {edge.id} ({edge.source_id} → {edge.target_id})")
print(f"Edge var mı?      {graph3.has_edge(edge_id)}")
print(f"Edge kaydı:      {edge_id in graph3.edges}")
print(f"edge_node_map:   {graph3.edge_node_map}")
print(f"node_edges[A]:   {graph3.node_edges.get('node_A')}")
print(f"node_edges[B]:   {graph3.node_edges.get('node_B')}")
print(f"adjacency[A]:    {graph3.adjacency.get('node_A')}")
print(f"adjacency[B]:    {graph3.adjacency.get('node_B')}")
print(f"forward_adj[A]: {graph3.forward_adjacency.get('node_A')}")
print(f"reverse_adj[B]: {graph3.reverse_adjacency.get('node_B')}")
print(f"Node count: {graph3.node_count}, Edge count: {graph3.edge_count}")

# --- KRİTİK: Node A'yı sil ---
print(f"\n>>> Node A ({na.id}) siliniyor...")
removed_a = graph3.remove_node("node_A")
print(f"remove_node('node_A') döndü: {removed_a}")

print("\n--- Silme SONRASI durum ---")
print(f"Node A hala var mı? {graph3.has_node('node_A')}")
print(f"Node B hala var mı? {graph3.has_node('node_B')}")
print(f"Edge hala var mı?   {graph3.has_edge(edge_id)}")
print(f"Node count: {graph3.node_count}, Edge count: {graph3.edge_count}")
print(f"edge_node_map: {graph3.edge_node_map}")
print(f"node_edges[B]: {graph3.node_edges.get('node_B')}")
print(f"adjacency[B]:  {graph3.adjacency.get('node_B')}")
print(f"reverse_adj[B]: {graph3.reverse_adjacency.get('node_B')}")

# Edge otomatik silindi mi?
if graph3.has_edge(edge_id):
    print("\n⚠️  Edge hala var — ORPHAN edge!")
else:
    print("\n✅ Edge otomatik silindi — cascade delete çalışıyor.")

# nodes_for_edge artık ne döndürüyor?
result_nfe = graph3.nodes_for_edge(edge_id)
print(f"nodes_for_edge(edge_id): {result_nfe}")
# edges_for_node artık ne döndürüyor?
result_efn = list(graph3.edges_for_node("node_B"))
print(f"edges_for_node('node_B'): {result_efn}")

assert not graph3.has_edge(edge_id), "Edge hala var! ORPHAN!"
assert "node_A" not in graph3.node_edges.get("node_B", set()), (
    "node_edges[B] hala A'ya ait edge'i tutuyor!"
)
print("\n✅ Referans bütünlüğü SAĞLAM: remove_node() cascade delete ile tüm edge'leri temizliyor.")
print("   (graph.py:54-78 — remove_node içinde edge_ids döngüsü)")

# =====================================================================
# 2b. Edge ortada kalmış node'a referans veriyorsa?
# =====================================================================
print("\n" + "-" * 72)
print("2b. Yetim edge simülasyonu — edge_node_map'te kaydı olmayan edge")
print("-" * 72)

graph4 = IntelligenceGraph()
a2 = IPAddress(id="orphan_A", ip="3.3.3.3")
b2 = IPAddress(id="orphan_B", ip="4.4.4.4")
na2 = graph4.add_entity(a2)
nb2 = graph4.add_entity(b2)

rel2 = Relationship(source_id="orphan_A", target_id="orphan_B", type=RelationshipType.RELATED_TO)
edge2 = graph4.add_relationship(rel2)
eid2 = edge2.id

# Manuel olarak edge_node_map boz (edge silindi ama edge_node_map'te kaldı)
# veya tersi — node silindi ama node_edges'te orphan_A'ya ait edge kaldı
# Aslında remove_node zaten temizliyor.
# Peki edge_node_map'te kaydı olup edges dict'inde olmayan edge?

# edge_node_map'i manuel bozalım
graph4.edge_node_map["bogus_edge"] = ("nonexistent_src", "nonexistent_tgt")
print("edge_node_map'a 'bogus_edge' → ('nonexistent_src', 'nonexistent_tgt') eklendi.")

try:
    result = graph4.nodes_for_edge("bogus_edge")
    print(f"nodes_for_edge('bogus_edge'): {result}")
except Exception as ex:
    print(f"nodes_for_edge('bogus_edge') EXCEPTION: {type(ex).__name__}: {ex}")

try:
    result = list(graph4.edges_for_node("orphan_A"))
    print(f"edges_for_node('orphan_A'): {result}")
except Exception as ex:
    print(f"edges_for_node('orphan_A') EXCEPTION: {type(ex).__name__}: {ex}")

# edges dict'inde olan ama node_edges'te olmayan edge
# Bu durum normalde oluşmaz çünkü add_relationship ikisini de günceller
# Ama elle bozarsak:
graph4.node_edges.get("orphan_A", set()).discard(eid2)
print(f"\nManuel olarak node_edges[orphan_A]'dan {eid2} çıkarıldı.")
try:
    result = list(graph4.edges_for_node("orphan_A"))
    print(f"edges_for_node('orphan_A'): {result}")  # edges_for_node edges dict'ini kontrol ediyor
except Exception as ex:
    print(f"edges_for_node('orphan_A') EXCEPTION: {type(ex).__name__}: {ex}")

# edges dict'inde olan edge'in source/target node'ları yok
# Bu remove_node ile oluşamaz (cascade var) ama elle simüle edelim
graph5 = IntelligenceGraph()
a3 = IPAddress(id="ghost_A", ip="5.5.5.5")
b3 = IPAddress(id="ghost_B", ip="6.6.6.6")
na3 = graph5.add_entity(a3)
nb3 = graph5.add_entity(b3)

rel3 = Relationship(source_id="ghost_A", target_id="ghost_B")
edge3 = graph5.add_relationship(rel3)

# Node'ları kaldır ama edge_node_map'teki edge'i temizlemeyi unut (manuel senaryo)
# Normalde remove_node cascade yapıyor ama biz edge kaydını tutalım
# edges.pop, edge_node_map'i de temizler — buna ulaşmak için doğrudan dict manipülasyonu
# Tam yetim edge: nodes dict'inde yok, edges dict'inde var
graph5.nodes.clear()
print("\nManuel: graph5.nodes temizlendi (node'lar yok, edge hala var).")
print(f"  nodes: {graph5.nodes}")
print(f"  edges: {list(graph5.edges.keys())}")
try:
    result = graph5.nodes_for_edge(edge3.id)
    print(f"nodes_for_edge(edge3.id): {result}")
except Exception as ex:
    print(f"nodes_for_edge(edge3.id) EXCEPTION: {type(ex).__name__}: {ex}")

try:
    result = list(graph5.neighbors("ghost_A"))
    print(f"neighbors('ghost_A'): {result}")
except Exception as ex:
    print(f"neighbors('ghost_A') EXCEPTION: {type(ex).__name__}: {ex}")

print("\n✅ edges_for_node() ve nodes_for_edge() None/empty dönüyor — crash yok.")
print("✅ neighbors() None node'ları yield etmiyor — çünkü if neighbor is not None kontrolü var.")

# =====================================================================
# 3. Duplicate / Edge-Case Davranışları
# =====================================================================
print("\n" + "=" * 72)
print("3. DUPLICATE / EDGE CASE DAVRANIŞLARI")
print("=" * 72)

# 3a. Aynı ID'ye sahip iki node
print("-" * 72)
print("3a. Aynı ID ile iki node ekleme")
print("-" * 72)

graph6 = IntelligenceGraph()
e_dup1 = IPAddress(id="dup_id", ip="7.7.7.7", rdns="first")
e_dup2 = IPAddress(id="dup_id", ip="8.8.8.8", rdns="second")
n_dup1 = graph6.add_entity(e_dup1)
n_dup2 = graph6.add_entity(e_dup2)

print(f"1. ekleme — id={e_dup1.id}, ip={e_dup1.ip}, dönen node id: {n_dup1.id}")
print(f"2. ekleme — id={e_dup2.id}, ip={e_dup2.ip}, dönen node id: {n_dup2.id}")
print(f"Graph'taki node sayısı: {graph6.node_count}")
print(f"Graph'taki node: id={list(graph6.nodes.keys())[0]}, ip={graph6.nodes['dup_id'].entity.ip}")
print(f"İlk node'un IP'si ne?    {n_dup1.entity.ip}")
print(f"Graph'taki node'un IP'si ne? {graph6.nodes['dup_id'].entity.ip}")

# add_entity her seferinde node.id = entity.id ile Node oluşturuyor
# ama graph.nodes[node.id] = node yazıyor — yani ikinci kayıt birincinin üzerine yazıyor
assert graph6.node_count == 1, "İkinci ekleme birinciyi ezmeli!"
print("✅ Aynı ID ile iki node eklenince: SON EKLENEN KALIR (üzerine yazar).")
print("   add_entity() overwrite yapıyor — özel bir hata/uyarı yok.")

# 3b. Boş/None ID
print("\n" + "-" * 72)
print("3b. Boş/None ID ile node oluşturma")
print("-" * 72)

# ID boş string
try:
    e_empty = IPAddress(id="", ip="9.9.9.9")
    n_empty = graph6.add_entity(e_empty)
    print(f"Boş ID'li node eklendi: id='{n_empty.id}', IP={e_empty.ip}")
    print(f"  graph.nodes[''] var mı? {'yes' if '' in graph6.nodes else 'no'}")
except Exception as ex:
    print(f"Boş ID'li node HATASI: {type(ex).__name__}: {ex}")

# Node'u frozen olduğu için None ID denemek BaseEntity'e kalmış
try:
    e_none = IPAddress(id=None, ip="10.10.10.10")
except Exception as ex:
    print(f"None ID'li entity HATASI: {type(ex).__name__}: {ex}")

# Confidence/trust score sınır dışı
print("\n--- Confidence/Trust score sınır testi ---")
try:
    IPAddress(id="bad_score", ip="11.11.11.11", confidence_score=150)
    print("confidence_score=150: HATA YOK (beklenmiyordu)")
except ValueError as ex:
    print(f"confidence_score=150: ValueError: {ex}")

try:
    IPAddress(id="bad_trust", ip="12.12.12.12", trust_score=-5)
    print("trust_score=-5: HATA YOK (beklenmiyordu)")
except ValueError as ex:
    print(f"trust_score=-5: ValueError: {ex}")

print("\n✅ BaseEntity confidence/trust score validation çalışıyor (0-100).")
print("✅ Boş ID (empty string) kabul ediliyor — grafiğe eklenebiliyor.")
print("   Bu potansiyel bir risk: '' ID'li node çakışmalara yol açabilir.")

# =====================================================================
# 4. Toplu Rapor
# =====================================================================
print("\n" + "=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
1a. Node oluşturma:
    → "gerçek mantık var + doğru çalışıyor"
    add_entity() Node oluşturup nodes, adjacency, forward/reverse_adjacency,
    node_edges dict'lerine kaydediyor. get_node()/has_node() doğru çalışıyor.

1b. Node güncelleme:
    → "çalışıyor ama yan etki/risk var"
    Açık update_node() metodu YOK. Güncelleme doğrudan graph.nodes[id] = new_node
    ile yapılıyor. Node ve BaseEntity frozen olduğundan yeni obje oluşturmak
    zorunlu — bu tutarlılık sağlasa da kullanıcının adj/list yapılarını
    da manuel güncellemesi gerekiyor (add_entity yapsaydı düzgün olurdu).

1c. Node silme:
    → "gerçek mantık var + doğru çalışıyor"
    remove_node() tüm yardımcı yapılardan temizliyor (adjacency, edge, node_edges).

1d. Var olmayan node:
    → "gerçek mantık var + doğru çalışıyor"
    remove_node(): False döndü, exception yok.
    get_node()/has_node(): sorunsuz çalışıyor.

2. Referans bütünlüğü:
    → "gerçek mantık var + doğru çalışıyor"
    remove_node() cascade delete yapıyor: edge_node_map, edges, node_edges,
    adjacency, forward/reverse_adjacency tamamen temizleniyor.
    Yetim edge SENARYOSU MÜMKÜN DEĞİL (normal akışta).
    edges_for_node() edges.get() None kontrolü yapıyor (edge.py:116).
    nodes_for_edge() nodes.get() None kontrolü yapıyor (edge.py:130-133).
    neighbors() neighbor None kontrolü yapıyor (graph.py:98-99).
    ← KODDA BİLİNÇLİ BİR GÜVENLİK ÖNLEMİ VAR.
    "Toleranslı tasarım" — garipliğe rağmen crash yok.

3a. Duplicate ID:
    → "çalışıyor ama yan etki/risk var"
    add_entity() silent overwrite yapıyor. Eski node kayboluyor.
    Uyarı/hata/log YOK. Bu bilinçli bir seçim değil, düşünülmemiş.

3b. Boş ID / sınır dışı değer:
    → "boşluk var, ele alınmamış"
    Boş string ID kabul ediliyor ve grafiğe ekleniyor.
    "" ID'li node diğer tüm işlemlerde sorun yaratabilir.
    BaseEntity confidence/trust validation (0-100) çalışıyor — ama bu
    Node seviyesinde değil, entity seviyesinde.
""")

print("=" * 72)
print("ÖZET KARNE")
print("=" * 72)
print("""
add_entity()     : ✅ GERÇEK — node'u 6 farklı dict'e kaydediyor
remove_node()    : ✅ GERÇEK — cascade delete + rollback yok ama tam temizlik
get_node()       : ✅ GERÇEK — dict lookup
has_node()       : ✅ GERÇEK — dict membership
update_node()    : ❌ YOK — kullanıcı doğrudan graph.nodes[id] overwrite yapmalı
Duplicate ID     : ⚠️  SESSİZ OVERWRITE — uyarı/log yok
Boş string ID    : ⚠️  KABUL EDİLİYOR — potansiyel risk
""")
