#!/usr/bin/env python3
"""
Doğrulama Testi — apply_change() döngü engelleme DÜZELTME SONRASI (v2)
"""

from __future__ import annotations

from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

engine = ArchitectureEvolutionEngine()

# Setup: DAG
engine.apply_change(
    engine.propose_architecture_change(
        "nlp→reasoning", "modify_dependencies", "nlp", ["reasoning"], 0.2
    ).proposal_id
)
engine.apply_change(
    engine.propose_architecture_change(
        "reasoning→execution", "modify_dependencies", "reasoning", ["execution"], 0.2
    ).proposal_id
)
engine.apply_change(
    engine.propose_architecture_change(
        "execution→governance", "modify_dependencies", "execution", ["governance"], 0.2
    ).proposal_id
)

print("=" * 72)
print("SENARYO A: governance→execution enjeksiyonu")
print("=" * 72)

topo_before = {k: list(v) for k, v in engine.get_topology().items()}
cycles_before = engine.detect_cycles()

prop = engine.propose_architecture_change(
    "INJECT: governance→execution",
    "modify_dependencies",
    "governance",
    ["metaintel", "execution"],
    risk_score=0.9,
)
result = engine.apply_change(prop.proposal_id)

topo_after = {k: list(v) for k, v in engine.get_topology().items()}
cycles_after = engine.detect_cycles()

print(f"apply_change() döndü: {result}")
print(
    f"Grafik değişmedi mi?   {'EVET (rollback çalıştı)' if topo_before == topo_after else 'HAYIR'}"
)
print(f"Sistem hala döngüsüz mü? {'EVET' if not cycles_after else 'HAYIR'}")
assert result is False, "❌ Döngülü değişiklik ENGELLENMEDİ!"
assert topo_before == topo_after, "❌ Rollback çalışmadı!"
assert not cycles_after, "❌ Sistem hala döngülü!"
print("✅ SENARYO A BAŞARILI\n")

print("=" * 72)
print("SENARYO B: circular_mod → execution, execution → circular_mod")
print("=" * 72)

engine.apply_change(
    engine.propose_architecture_change(
        "add circular_mod→execution",
        "add_module",
        "circular_mod",
        new_dependencies=["execution"],
        risk_score=0.3,
    ).proposal_id
)

topo_before2 = {k: list(v) for k, v in engine.get_topology().items()}
cycles_before2 = engine.detect_cycles()

prop2 = engine.propose_architecture_change(
    "INJECT: execution→circular_mod",
    "modify_dependencies",
    "execution",
    ["governance", "circular_mod"],
    risk_score=0.9,
)
result2 = engine.apply_change(prop2.proposal_id)

topo_after2 = {k: list(v) for k, v in engine.get_topology().items()}
cycles_after2 = engine.detect_cycles()

print(f"apply_change() döndü: {result2}")
print(
    f"Grafik değişmedi mi?   {'EVET (rollback çalıştı)' if topo_before2 == topo_after2 else 'HAYIR'}"
)
print(f"Sistem hala döngüsüz mü? {'EVET' if not cycles_after2 else 'HAYIR'}")
assert result2 is False, "❌ Döngülü değişiklik ENGELLENMEDİ!"
assert topo_before2 == topo_after2, "❌ Rollback çalışmadı!"
assert not cycles_after2, "❌ Sistem hala döngülü!"
print("✅ SENARYO B BAŞARILI\n")

print("=" * 72)
print("REGRESYON: geçerli değişiklikler hala çalışıyor mu?")
print("=" * 72)

# Test 1: modify_dependencies - cycle-free (metaintel→storage)
r1 = engine.apply_change(
    engine.propose_architecture_change(
        "metaintel→storage (valid)", "modify_dependencies", "metaintel", ["storage"], 0.1
    ).proposal_id
)
print(f"modify_dependencies (metaintel→storage):   {r1}")
assert r1, "FAIL"

# Test 2: add_module - cycle-free
r2 = engine.apply_change(
    engine.propose_architecture_change(
        "add new_module→storage", "add_module", "new_module", ["storage"], 0.1
    ).proposal_id
)
print(f"add_module (new_module→storage):            {r2}")
assert r2, "FAIL"

# Test 3: remove_module
r3 = engine.apply_change(
    engine.propose_architecture_change(
        "remove new_module", "remove_module", "new_module", risk_score=0.1
    ).proposal_id
)
print(f"remove_module (new_module):                 {r3}")
assert r3, "FAIL"

# Test 4: modify_dependencies - set empty
r4 = engine.apply_change(
    engine.propose_architecture_change(
        "metaintel→ (empty, valid)", "modify_dependencies", "metaintel", [], 0.1
    ).proposal_id
)
print(f"modify_dependencies (metaintel→empty):      {r4}")
assert r4, "FAIL"

# Test 5: add_module with no deps
r5 = engine.apply_change(
    engine.propose_architecture_change(
        "add standalone→ (empty)", "add_module", "standalone", [], 0.1
    ).proposal_id
)
print(f"add_module (standalone→empty):              {r5}")
assert r5, "FAIL"

# Test 6: modify_dependencies on standalone with valid deps
r6 = engine.apply_change(
    engine.propose_architecture_change(
        "standalone→api (valid)", "modify_dependencies", "standalone", ["api"], 0.1
    ).proposal_id
)
print(f"modify_dependencies (standalone→api):       {r6}")
assert r6, "FAIL"

# Test 7: modify_dependencies on nlp (change from reasoning to metaintel)
r7 = engine.apply_change(
    engine.propose_architecture_change(
        "nlp→metaintel (valid)", "modify_dependencies", "nlp", ["metaintel"], 0.1
    ).proposal_id
)
print(f"modify_dependencies (nlp→metaintel):        {r7}")
assert r7, "FAIL"

# DAG hala temiz mi?
final_cycles = engine.detect_cycles()
print(f"\nTüm işlemler sonrası döngü: {'YOK' if not final_cycles else 'VAR'}")
if final_cycles:
    print(f"  Döngü: {final_cycles}")
assert not final_cycles, "Döngü olmamalı!"

print("✅ TÜM REGRESYON TESTLERİ GEÇTİ")
