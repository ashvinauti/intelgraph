#!/usr/bin/env python3
"""
graph.add_entity Düzeltme Doğrulaması — Duplicate + Boş ID
Mock'suz, gerçek veriyle, bağımsız.
"""

from __future__ import annotations

import io
import logging

from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.graph import IntelligenceGraph

print("=" * 72)
print("1. DUPLICATE ID — varsayılan davranış (overwrite=False, merge)")
print("=" * 72)

# Logları yakala
log_capture = io.StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.INFO)
logging.getLogger("intelgraph.core.graph.graph").addHandler(handler)
logging.getLogger("intelgraph.core.graph.graph").setLevel(logging.INFO)

graph = IntelligenceGraph()
e1 = IPAddress(
    id="dup_test", ip="10.0.0.1", rdns="first.example.com", confidence_score=80, trust_score=70
)
e2 = IPAddress(
    id="dup_test", ip="10.0.0.2", rdns="second.example.com", confidence_score=90, trust_score=85
)

n1 = graph.add_entity(e1)
n2 = graph.add_entity(e2)

print(f"Eklenen node'lar aynı ID: {n1.id} == {n2.id}")
print(f"Graph node sayısı:         {graph.node_count}")
print(f"Mevcut node IP:           {graph.nodes['dup_test'].entity.ip}")
print(f"Mevcut node rdns:         {graph.nodes['dup_test'].entity.rdns}")
print(f"Mevcut node confidence:   {graph.nodes['dup_test'].entity.confidence_score}")
print(f"Mevcut node trust:        {graph.nodes['dup_test'].entity.trust_score}")

# previous_versions kontrolü
prev = graph.previous_versions.get("dup_test", [])
print(f"\nprevious_versions['dup_test']: {len(prev)} eski versiyon")
if prev:
    old = prev[0]
    print(f"  Eski IP:   {old.entity.ip}")
    print(f"  Eski rdns: {old.entity.rdns}")
    print(f"  Eski confidence: {old.entity.confidence_score}")

assert graph.node_count == 1, "Hala tek node olmalı!"
assert graph.nodes["dup_test"].entity.ip == "10.0.0.2", "Yeni IP gelmeli!"
assert len(prev) == 1, "Eski versiyon kaydedilmeli!"
assert prev[0].entity.ip == "10.0.0.1", "Eski versiyon IP korunmalı!"

# Log kontrolü
log_output = log_capture.getvalue()
print(f"\nLog çıktısı: {log_output.strip()}")
assert "already exists, merging" in log_output, "Log mesajı üretilmeli!"
print("✅ Duplicate ID: merge yapıldı, eski versiyon previous_versions'da korunuyor, log üretildi.")

# =====================================================================
print("\n" + "=" * 72)
print("2. overwrite=True — eski davranış (sessiz üzerine yazma)")
print("=" * 72)

log_capture2 = io.StringIO()
handler2 = logging.StreamHandler(log_capture2)
handler2.setLevel(logging.INFO)
logging.getLogger("intelgraph.core.graph.graph").addHandler(handler2)

graph2 = IntelligenceGraph()
e3 = IPAddress(id="ow_test", ip="1.1.1.1", rdns="old")
e4 = IPAddress(id="ow_test", ip="9.9.9.9", rdns="new")

n3 = graph2.add_entity(e3)
n4 = graph2.add_entity(e4, overwrite=True)

print(f"Graph node sayısı:                {graph2.node_count}")
print(f"Mevcut node IP:                   {graph2.nodes['ow_test'].entity.ip}")
print(f"previous_versions kaydı var mı?   {'ow_test' in graph2.previous_versions}")

log2 = log_capture2.getvalue()
print(f"Log çıktısı: {log2.strip()}")

assert graph2.node_count == 1
assert graph2.nodes["ow_test"].entity.ip == "9.9.9.9"
assert "ow_test" not in graph2.previous_versions, (
    "overwrite=True ise previous_versions'a kaydedilmemeli!"
)
assert "overwriting" in log2, "overwrite log'u üretilmeli!"
print("✅ overwrite=True: eski davranış korunuyor, previous_versions kaydı YOK.")

# =====================================================================
print("\n" + "=" * 72)
print("3. BOŞ/None ID reddediliyor mu?")
print("=" * 72)

graph3 = IntelligenceGraph()

try:
    e_bad = IPAddress(id="", ip="0.0.0.0")
    graph3.add_entity(e_bad)
    print("❌ Boş string ID KABUL EDİLDİ (beklenmiyordu)!")
    raise AssertionError("Boş ID kabul edilmemeli!")
except ValueError as ex:
    print(f"Boş string ID → ValueError: {ex}")
    print("✅ Reddedildi.")

try:
    e_none = IPAddress(id=None, ip="0.0.0.0")
    graph3.add_entity(e_none)
    print("❌ None ID KABUL EDİLDİ (beklenmiyordu)!")
    raise AssertionError("None ID kabul edilmemeli!")
except (ValueError, TypeError) as ex:
    print(f"None ID → {type(ex).__name__}: {ex}")
    print("✅ Reddedildi.")

# Boş ID'den sonra graf temiz kaldı mı?
print(f"Graph node sayısı: {graph3.node_count}")
assert graph3.node_count == 0
print("✅ Hatalı eklemeler grafiği etkilemedi.")

# =====================================================================
print("\n" + "=" * 72)
print("4. remove_node previous_versions'ı temizliyor mu?")
print("=" * 72)

graph4 = IntelligenceGraph()
e5 = IPAddress(id="clean_test", ip="1.2.3.4")
e6 = IPAddress(id="clean_test", ip="5.6.7.8")
graph4.add_entity(e5)
graph4.add_entity(e6)  # merge — previous_versions'a kaydeder

print(f"Silme öncesi previous_versions: {dict(graph4.previous_versions)}")
assert "clean_test" in graph4.previous_versions

removed = graph4.remove_node("clean_test")
print(f"remove_node döndü: {removed}")
print(f"Silme sonrası previous_versions: {dict(graph4.previous_versions)}")
assert "clean_test" not in graph4.previous_versions, (
    "remove_node previous_versions'ı da temizlemeli!"
)
print("✅ remove_node previous_versions'ı da temizliyor (graph.py'ye eklendi).")

# =====================================================================
print("\n" + "=" * 72)
print("5. OVERWRITE FALSE + duplicate log seviyesi")
print("=" * 72)

log_capture3 = io.StringIO()
handler3 = logging.StreamHandler(log_capture3)
handler3.setLevel(logging.DEBUG)
logging.getLogger("intelgraph.core.graph.graph").addHandler(handler3)

graph5 = IntelligenceGraph()
graph5.add_entity(IPAddress(id="log_test", ip="1.1.1.1"))
graph5.add_entity(IPAddress(id="log_test", ip="2.2.2.2"))

log3 = log_capture3.getvalue()
print(f"Log: {log3.strip()}")
assert "merging" in log3
print("✅ Log mesajı üretildi, içerik açık.")

# =====================================================================
print("\n" + "=" * 72)
print("SONUÇ")
print("=" * 72)
print("""
1. Duplicate ID (overwrite=False):
   → "gerçek mantık var + doğru çalışıyor"
   Eski node previous_versions'a kaydediliyor, yeni node graph'a yazılıyor.
   Log üretiliyor. Veri kaybı yok.

2. overwrite=True:
   → "gerçek mantık var + doğru çalışıyor"
   Eski davranış korunuyor, previous_versions kaydı yok.
   Log üretiliyor.

3. Boş/None ID reddi:
   → "gerçek mantık var + doğru çalışıyor"
   ValueError fırlatılıyor, grafik etkilenmiyor.

4. remove_node temizliği:
   → "gerçek mantık var + doğru çalışıyor"
   previous_versions da temizleniyor.

5. Log seviyesi:
   → "gerçek mantık var + doğru çalışıyor"
   INFO seviyesinde, açık mesaj.
""")
