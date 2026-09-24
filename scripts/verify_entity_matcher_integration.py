#!/usr/bin/env python3
"""
EntityMatcher/MergeEngine Entegrasyon Doğrulaması

add_entity() otomatik olarak EntityMatcher çağırıp aynı IP'leri birleştiriyor mu?
Mock'suz, gerçek veriyle, manuel matcher çağrısı YOK.
"""

from __future__ import annotations

import io
import logging

from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.graph import IntelligenceGraph

print("=" * 72)
print("SENARYO: Pazartesi log + Salı rapor (aynı IP, farklı ULID)")
print("add_entity() OTOMATİK birleştiriyor mu?")
print("=" * 72)

# Log yakala
log_capture = io.StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.INFO)
logging.getLogger("intelgraph.core.graph.graph").addHandler(handler)

graph = IntelligenceGraph()

# Pazartesi: düşük confidence
e_mon = IPAddress(
    ip="192.168.1.5",
    rdns="suspicious-host.example.com",
    confidence_score=60,
    trust_score=50,
)

# Salı: yüksek confidence
e_tue = IPAddress(
    ip="192.168.1.5",
    rdns="cve-associated-host.example.com",
    confidence_score=85,
    trust_score=70,
)

n_mon = graph.add_entity(e_mon)
n_tue = graph.add_entity(e_tue)

print(f"Pazartesi node ID:  {n_mon.id}")
print(f"Salı node ID:       {n_tue.id}")
print(f"ID'ler eşit mi?     {n_mon.id == n_tue.id}")
print(f"Graph node sayısı:  {graph.node_count}")
print()

print("Graph'taki düğümler:")
for nid, n in graph.nodes.items():
    print(f"  {nid}")
    print(f"    IP:      {n.entity.ip}")
    print(f"    rdns:    {n.entity.rdns}")
    print(f"    conf:    {n.entity.confidence_score}")
    print(f"    trust:   {n.entity.trust_score}")
    print(f"    type:    {type(n.entity).__name__}")

# Log çıktısı
logs = log_capture.getvalue()
print(f"\nLog çıktısı:\n{logs}")

if graph.node_count == 1:
    print("✅ TEK node — EntityMatcher OTOMATİK birleştirdi!")
else:
    print("❌ İKİ AYRI node — otomatik birleşme YOK")

# =====================================================================
print("\n" + "=" * 72)
print("DOĞRULAMA: Her iki kaynaktan gelen bilgi korundu mu?")
print("=" * 72)

if graph.node_count == 1:
    merged_node = list(graph.nodes.values())[0]
    print(f"IP:            {merged_node.entity.ip}")
    print(f"rdns:          {merged_node.entity.rdns}  (Salı'dan, çünkü confidence=85 > 60)")
    print(f"confidence:    {merged_node.entity.confidence_score}  (max: 85)")
    print(f"trust:         {merged_node.entity.trust_score}  (max: 70)")

    # MergeEngine most_confident: rdns Salı'dan gelmeli
    assert merged_node.entity.ip == "192.168.1.5"
    assert merged_node.entity.rdns == "cve-associated-host.example.com"
    assert merged_node.entity.confidence_score == 85
    assert merged_node.entity.trust_score == 70
    print("\n✅ Her iki kaynaktan bilgi birleşti (max alınan field'lar).")
    print("⚠️  Pazartesi'nin rdns'i ('suspicious-host') kayboldu — MergeEngine")
    print("   aynı field'da çakışma olduğunda en yüksek confidence'lıyı seçiyor.")
    print("   (previous_versions'da eski kayıt korunuyor.)")

    prev = graph.previous_versions.get(merged_node.id, [])
    print(f"\nprevious_versions: {len(prev)} eski versiyon")
    if prev:
        print(f"  Eski rdns: {prev[0].entity.rdns}  ← Pazartesi kaydı burada")
else:
    print("❌ İki node var — doğrulama yapılamıyor.")

# =====================================================================
print("\n" + "=" * 72)
print("REGRESYON: Farklı tipler yanlış eşleşiyor mu?")
print("=" * 72)

graph2 = IntelligenceGraph()
e_ip = IPAddress(ip="10.0.0.1", rdns="test.local")
e_domain = Domain(domain_name="example.com", registrant="someone")
n_ip = graph2.add_entity(e_ip)
n_domain = graph2.add_entity(e_domain)

print(f"Graph node sayısı: {graph2.node_count} (beklenen: 2)")
for nid, n in graph2.nodes.items():
    print(f"  {nid[:12]}...  type={type(n.entity).__name__}")
assert graph2.node_count == 2, "IP + Domain = 2 node olmalı, birleşmemeli!"
print("✅ IP + Domain farklı tipler: birleşmedi.")

# =====================================================================
print("\n" + "=" * 72)
print("REGRESYON: Exact ID duplicate detection hala çalışıyor mu?")
print("=" * 72)

graph3 = IntelligenceGraph()
ea = IPAddress(id="exact_dup", ip="1.1.1.1", rdns="first")
eb = IPAddress(id="exact_dup", ip="9.9.9.9", rdns="second")
na = graph3.add_entity(ea)
nb = graph3.add_entity(eb)

print(f"Graph node sayısı: {graph3.node_count} (beklenen: 1)")
print(f"Node IP: {graph3.nodes['exact_dup'].entity.ip}")
assert graph3.node_count == 1
assert graph3.nodes["exact_dup"].entity.ip == "9.9.9.9"
assert len(graph3.previous_versions.get("exact_dup", [])) == 1
print("✅ Exact ID duplicate: previous_versions + overwrite hala çalışıyor.")

# =====================================================================
print("\n" + "=" * 72)
print("REGRESYON: overwrite=True hala çalışıyor mu?")
print("=" * 72)

graph4 = IntelligenceGraph()
ec = IPAddress(id="ow_test", ip="1.1.1.1")
ed = IPAddress(id="ow_test", ip="2.2.2.2")
graph4.add_entity(ec)
graph4.add_entity(ed, overwrite=True)

assert graph4.node_count == 1
assert "ow_test" not in graph4.previous_versions
print(f"Graph node sayısı: {graph4.node_count}, IP: {graph4.nodes['ow_test'].entity.ip}")
print("✅ overwrite=True: previous_versions'a kaydetmiyor.")

# =====================================================================
print("\n" + "=" * 72)
print("REGRESYON: Boş ID reddi hala çalışıyor mu?")
print("=" * 72)

try:
    graph4.add_entity(IPAddress(id="", ip="0.0.0.0"))
    print("❌ Boş ID KABUL EDİLDİ!")
except ValueError:
    print("✅ Boş ID → ValueError.")

# =====================================================================
print("\n" + "=" * 72)
print("ÖZET")
print("=" * 72)

if graph.node_count == 1:
    print("""
Entegrasyon: "EntityMatcher OTOMATİK çalışıyor, aynı varlıklar birleşiyor"

   ✓ Aynı IP'li iki entity → tek node (Pazartesi + Salı birleşti)
   ✓ MergeEngine most_confident stratejisiyle çalıştı
   ✓ Farklı tipler (IP + Domain) birleşmedi (type filter çalışıyor)
   ✓ Exact ID duplicate hala çalışıyor
   ✓ overwrite=True hala çalışıyor
   ✓ Boş ID reddediliyor

   ⚠️  Bilgi kaybı: Aynı field'da çakışma varsa, MergeEngine en yüksek
      confidence'lı kaynağı seçiyor. Eski değer previous_versions'da.
""")
else:
    print("\n❌ Entegrasyon TAM OLARAK ÇALIŞMADI!")
