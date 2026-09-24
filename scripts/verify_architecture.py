#!/usr/bin/env python3
"""
Bağımsız Gerçek Davranış Doğrulama Testi — architecture.py

Mevcut hiçbir unit test referans alınmamıştır.
Mock kullanılmamıştır. Gerçek ArchitectureEvolutionEngine ile çalışılır.
"""

from __future__ import annotations

import sys

# --- Gerçek modülü import et ---
from intelgraph.core.metaintel.architecture import (
    ArchitectureEvolutionEngine,
)

engine = ArchitectureEvolutionEngine()

# =====================================================================
# ADIM 1: Gerçek bağımlılık grafiği oluştur
# AIOS projesinin soyut modül yapısını yansıtan gerçekçi bir DAG
# =====================================================================
print("=" * 72)
print("ADIM 1: Gerçekçi bağımlılık grafiği kuruluyor...")
print("=" * 72)

# Varsayılan modüller: nlp, reasoning, execution, governance, metaintel, storage, api
# Bunlar zaten _register_default_modules() ile kayıtlı.
# Şimdi gerçekçi bağımlılıklar ekleyelim:

engine.apply_change(
    engine.propose_architecture_change(
        "Set NLP→reasoning dependency",
        "modify_dependencies",
        "nlp",
        new_dependencies=["reasoning"],
        risk_score=0.2,
    ).proposal_id
)

engine.apply_change(
    engine.propose_architecture_change(
        "Set reasoning→execution dependency",
        "modify_dependencies",
        "reasoning",
        new_dependencies=["execution"],
        risk_score=0.2,
    ).proposal_id
)

engine.apply_change(
    engine.propose_architecture_change(
        "Set execution→governance dependency",
        "modify_dependencies",
        "execution",
        new_dependencies=["governance"],
        risk_score=0.2,
    ).proposal_id
)

engine.apply_change(
    engine.propose_architecture_change(
        "Set governance→metaintel dependency",
        "modify_dependencies",
        "governance",
        new_dependencies=["metaintel"],
        risk_score=0.2,
    ).proposal_id
)

engine.apply_change(
    engine.propose_architecture_change(
        "Set storage dependency",
        "modify_dependencies",
        "storage",
        new_dependencies=[],
        risk_score=0.1,
    ).proposal_id
)

engine.apply_change(
    engine.propose_architecture_change(
        "Set api dependency",
        "modify_dependencies",
        "api",
        new_dependencies=["storage"],
        risk_score=0.1,
    ).proposal_id
)

topology = engine.get_topology()
print("\nOluşan bağımlılık grafiği (DAG):")
for mod, deps in sorted(topology.items()):
    print(f"  {mod:15s} → {deps}")

# Döngü kontrolü
cycles = engine.detect_cycles()
print(f"\nDöngü var mı? {'EVET' if cycles else 'HAYIR'}")
assert not cycles, f"Beklenmeyen döngü bulundu: {cycles}"
print("✅ DAG doğrulandı: döngü yok.\n")

# =====================================================================
# ADIM 2: Bilerek döngü enjekte et — A → B → C → A
# =====================================================================
print("=" * 72)
print("ADIM 2: Döngü enjekte ediliyor (execution → nlp)...")
print("=" * 72)

engine.apply_change(
    engine.propose_architecture_change(
        "INJECT CYCLE: execution → nlp",
        "modify_dependencies",
        "execution",
        new_dependencies=[
            "governance",
            "nlp",
        ],  # nlp zaten execution'a bağımlı değil ama execution→nlp olunca döngü: nlp→reasoning→execution→nlp
        risk_score=1.0,
    ).proposal_id
)

topology = engine.get_topology()
print("\nDöngü enjekte edilmiş grafik:")
for mod, deps in sorted(topology.items()):
    print(f"  {mod:15s} → {deps}")

cycles = engine.detect_cycles()
print(f"\nDöngü bulundu: {'EVET' if cycles else 'HAYIR'}")
print(f"Ham çıktı (cycles): {cycles}")

# Beklenen: NLP→REASONING→EXECUTION→NLP (veya varyantı)
if cycles:
    for c in cycles:
        path_str = " → ".join(c)
        print(f"  Döngü yolu: {path_str}")
    print("✅ Döngü başarıyla TESPİT EDİLDİ.")
else:
    print("❌ HATA: Döngü TESPİT EDİLEMEDİ!")
    sys.exit(1)

# =====================================================================
# ADIM 3: Döngüyü kaldır, yeni bir 2-düğümlü döngü ekle
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 3: 2-düğümlü döngü testi (api ↔ storage)...")
print("=" * 72)

# Önce execution'ı düzelt
engine.apply_change(
    engine.propose_architecture_change(
        "Fix execution dependency (remove cycle)",
        "modify_dependencies",
        "execution",
        new_dependencies=["governance"],
        risk_score=0.2,
    ).proposal_id
)

# api zaten storage'a bağımlı, şimdi storage'ı da api'ye bağımlı yapalım
engine.apply_change(
    engine.propose_architecture_change(
        "INJECT CYCLE: storage → api",
        "modify_dependencies",
        "storage",
        new_dependencies=["api"],
        risk_score=1.0,
    ).proposal_id
)

topology = engine.get_topology()
print("\n2-düğümlü döngü grafiği:")
for mod, deps in sorted(topology.items()):
    print(f"  {mod:15s} → {deps}")

cycles = engine.detect_cycles()
print(f"\nDöngü bulundu: {'EVET' if cycles else 'HAYIR'}")
print(f"Ham çıktı (cycles): {cycles}")

if cycles:
    for c in cycles:
        path_str = " → ".join(c)
        print(f"  Döngü yolu: {path_str}")
    print("✅ 2-düğümlü döngü başarıyla TESPİT EDİLDİ.")
else:
    print("❌ HATA: 2-düğümlü döngü TESPİT EDİLEMEDİ!")
    sys.exit(1)

# =====================================================================
# ADIM 4: Modül ekleme fonksiyonu testi
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 4: apply_change(add_module) davranış testi...")
print("=" * 72)

module_count_before = len(engine.get_modules())
topo_count_before = len(engine.get_topology())

proposal = engine.propose_architecture_change(
    "Add new AI verification module",
    "add_module",
    "ai_verifier",
    new_dependencies=["reasoning", "storage"],
    risk_score=0.4,
)
applied = engine.apply_change(proposal.proposal_id)
print(f"apply_change döndü: {applied}")
assert applied, "apply_change BAŞARISIZ!"

module_count_after = len(engine.get_modules())
topo_count_after = len(engine.get_topology())

print(f"Modül sayısı: {module_count_before} → {module_count_after}")
print(f"Grafik düğüm sayısı: {topo_count_before} → {topo_count_after}")
assert module_count_after == module_count_before + 1, "Modül eklenmedi!"
assert topo_count_after == topo_count_before + 1, "Grafik düğümü eklenmedi!"

# Eklenen modülün detaylarını kontrol et
modules = {m.module_id: m for m in engine.get_modules()}
assert "ai_verifier" in modules, "ai_verifier modül olarak kayıtlı değil!"
verifier = modules["ai_verifier"]
print(f"  module_id: {verifier.module_id}")
print(f"  name:       {verifier.name}")
print(f"  type:       {verifier.module_type}")
print(f"  status:     {verifier.status}")
print(f"  deps:       {verifier.dependencies}")
print(f"  health:     {verifier.health_score}")
print(f"  version:    {verifier.version}")
assert verifier.module_type == "custom"
assert verifier.status == "active"
assert "reasoning" in verifier.dependencies
assert "storage" in verifier.dependencies
assert verifier.health_score == 0.8
print("✅ add_module: modül GERÇEKTEN sisteme eklendi.")

# =====================================================================
# ADIM 5: Modül çıkarma fonksiyonu testi
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 5: apply_change(remove_module) davranış testi...")
print("=" * 72)

module_count_before = len(engine.get_modules())
topo_count_before = len(engine.get_topology())

proposal = engine.propose_architecture_change(
    "Remove AI verification module",
    "remove_module",
    "ai_verifier",
    risk_score=0.2,
)
applied = engine.apply_change(proposal.proposal_id)
print(f"apply_change döndü: {applied}")
assert applied

module_count_after = len(engine.get_modules())
topo_count_after = len(engine.get_topology())
print(f"Modül sayısı: {module_count_before} → {module_count_after}")
print(f"Grafik düğüm sayısı: {topo_count_before} → {topo_count_after}")
assert module_count_after == module_count_before - 1, "Modül silinmedi!"
assert topo_count_after == topo_count_before - 1, "Grafik düğümü silinmedi!"
assert "ai_verifier" not in {m.module_id for m in engine.get_modules()}
print("✅ remove_module: modül GERÇEKTEN sistemden silindi.")

# Diğer modüllerden referansların temizlendiğini kontrol et
topology = engine.get_topology()
for mod, deps in topology.items():
    assert "ai_verifier" not in deps, f"{mod} hala ai_verifier'a referans veriyor!"
print("✅ remove_module: bağımlılık referansları da temizlendi.")

# =====================================================================
# ADIM 6: Yazılım Mimarisi Analizi
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 6: Kod analizi — Gerçek graph algoritması var mı?")
print("=" * 72)

import inspect

from intelgraph.core.metaintel import architecture as arch_mod

# detect_cycles kaynak kodunu incele
source = inspect.getsource(arch_mod.ArchitectureEvolutionEngine.detect_cycles)
print("\n--- detect_cycles() kaynak kodu ---")
for line in source.split("\n"):
    print(f"  {line}")

# Algoritma kontrolü
has_dfs = "def _dfs" in source
has_visited_set = "visited:" in source or "visited =" in source
has_recursion_stack = "in_stack" in source
has_cycle_construct = "cycle_start" in source and "path.index" in source

print(f"\n  DFS fonksiyonu var mı?      {'EVET' if has_dfs else 'HAYIR'}")
print(f"  visited set'i var mı?         {'EVET' if has_visited_set else 'HAYIR'}")
print(f"  recursion stack var mı?       {'EVET' if has_recursion_stack else 'HAYIR'}")
print(f"  Döngü yolu oluşturma var mı?  {'EVET' if has_cycle_construct else 'HAYIR'}")

assert has_dfs, "❌ GERÇEK DFS ALGORİTMASI YOK!"
assert has_visited_set, "❌ visited set'i yok!"
assert has_recursion_stack, "❌ recursion stack yok!"
assert has_cycle_construct, "❌ cycle path oluşturma yok!"

# apply_change kaynak kodu
print("\n--- apply_change() kaynak kodu ---")
source_ac = inspect.getsource(arch_mod.ArchitectureEvolutionEngine.apply_change)
for line in source_ac.split("\n"):
    print(f"  {line}")

# =====================================================================
# SONUÇ
# =====================================================================
print("\n" + "=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
KATEGORİ 1 — Döngü tespiti:
  → "gerçek mantık var + çalışıyor"
  Kanıt: DFS tabanlı recursive cycle detection (in_stack set'i ile).
  Hem 2-düğümlü (api↔storage) hem 3+-düğümlü (nlp→reasoning→execution→nlp)
  döngüleri başarıyla buldu. Topolojinin tamamını tarıyor.

KATEGORİ 2 — Modül ekleme/çıkarma:
  → "gerçek mantık var + çalışıyor"
  Kanıt: apply_change() içinde self._modules dict'ine gerçek ArchitectureModule
  objesi ekleniyor, self._dependency_graph güncelleniyor, topology_history
  kaydı tutuluyor. remove_module'de referanslar temizleniyor.

KATEGORİ 3 — Graph algoritması:
  → "gerçek mantık var + çalışıyor"
  Kanıt: lines 141-163 — gerçek DFS (depth-first search) implementasyonu.
  visited set, recursion stack (in_stack), path listesi ile çalışan
  standart directed graph cycle detection algoritması.
  Sabit/placeholder dönüş yok, gerçek graph üzerinde işlem yapıyor.
""")
