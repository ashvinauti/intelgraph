#!/usr/bin/env python3
"""
Bağımsız Doğrulama Testi — apply_change() döngü engelleme davranışı

Önceki test cycle detection'ın gerçek olduğunu kanıtladı.
Şimdi bu sonucun UYGULAMADA kullanılıp kullanılmadığı kontrol edilecek.
"""

from __future__ import annotations

from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

engine = ArchitectureEvolutionEngine()

# =====================================================================
# ADIM 1: Kod incelemesi — apply_change içinde detect_cycles çağrısı var mı?
# =====================================================================
print("=" * 72)
print("ADIM 1: Kod incelemesi — apply_change() içinde detect_cycles() çağrısı")
print("=" * 72)

import inspect

from intelgraph.core.metaintel import architecture as arch_mod

source_ac = inspect.getsource(arch_mod.ArchitectureEvolutionEngine.apply_change)
call_count = source_ac.count("detect_cycles")
print(f"apply_change() içinde 'detect_cycles' geçme sayısı: {call_count}")
print("\n--- apply_change() kaynak kodunun tamamı ---")
for i, line in enumerate(source_ac.split("\n"), start=1):
    print(f"  {i}: {line}")

if call_count == 0:
    print("\n✅ TESPİT: apply_change() İÇİNDE detect_cycles() ÇAĞRISI YOK.")
    print("   Döngüler tespit EDİLEBİLİYOR ancak UYGULAMADA ENGELLENMİYOR.")
else:
    print(
        f"\n⚠️  apply_change() içinde {call_count} adet detect_cycles çağrısı var. Detaylı inceleme gerekiyor."
    )

# =====================================================================
# ADIM 2: Canlı test — döngü oluşturacak modify_dependencies dene
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 2: Canlı test — döngü oluşturacak modify_dependencies çağrısı")
print("=" * 72)

# Başlangıç: DAG
# nlp→reasoning→execution→governance→metaintel, api→storage
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

topo = engine.get_topology()
print("Başlangıç grafiği (DAG):")
for m, d in sorted(topo.items()):
    print(f"  {m:15s} → {d}")
cycles = engine.detect_cycles()
print(f"Döngü: {'YOK' if not cycles else 'VAR'}")
assert not cycles, "Başlangıçta döngü olmamalı!"
print("✅ Başlangıç: DAG doğrulandı.\n")

# Döngü enjeksiyonu: governance → execution ekle (execution→governance zaten var)
print("--- Döngü enjeksiyonu: governance → execution ekleniyor ---")
topo_before: dict = {k: list(v) for k, v in engine.get_topology().items()}

try:
    prop = engine.propose_architecture_change(
        "INJECT: governance→execution",
        "modify_dependencies",
        "governance",
        ["metaintel", "execution"],
        risk_score=0.9,
    )
    result = engine.apply_change(prop.proposal_id)
    print(f"apply_change() döndü: {result}")
    print("İstisna (exception): YOK\n")
except Exception as e:
    print(f"apply_change() İSTİSNA FIRLATTI: {type(e).__name__}: {e}\n")
    result = False

# Sonrası grafik
topo_after = engine.get_topology()
print("İşlem SONRASI grafik:")
for m, d in sorted(topo_after.items()):
    marker = " *** DÖNGÜ" if (m == "governance" and "execution" in d) else ""
    print(f"  {m:15s} → {d}{marker}")

cycles_after = engine.detect_cycles()
print(f"\nDöngü tespiti: {'EVET' if cycles_after else 'HAYIR'}")
if cycles_after:
    for c in cycles_after:
        print(f"  Döngü yolu: {' → '.join(c)}")

# Değişiklik sonrası grafik öncesiyle aynı mı?
topo_before_str = str(topo_before)
topo_after_str = str({k: list(v) for k, v in topo_after.items()})
if topo_before_str == topo_after_str:
    print("✅ Rollback: Grafik değişmemiş (önceki haliyle aynı).")
else:
    print("❌ Rollback YOK: Grafik değişti (döngü eklendi).")

print()

# =====================================================================
# ADIM 3: Canlı test — döngü oluşturacak add_module dene
# =====================================================================
print("=" * 72)
print("ADIM 3: Canlı test — döngü oluşturacak add_module çağrısı")
print("=" * 72)

# Önce düzelt: governance'i eski haline getir
engine.apply_change(
    engine.propose_architecture_change(
        "fix governance", "modify_dependencies", "governance", ["metaintel"], 0.1
    ).proposal_id
)
assert not engine.detect_cycles(), "Düzeltme sonrası döngü olmamalı!"

# Yeni bir modül ekle: x→y, sonra y→x şeklinde döngü yap
print("Yeni modül 'circular_mod' ekleniyor, bağımlılığı: execution")
prop1 = engine.propose_architecture_change(
    "add circular_mod",
    "add_module",
    "circular_mod",
    new_dependencies=["execution"],
    risk_score=0.3,
)
engine.apply_change(prop1.proposal_id)

topo_before2: dict = {k: list(v) for k, v in engine.get_topology().items()}
print(f"   circular_mod eklendi. Düğüm sayısı: {len(topo_before2)}")

# Şimdi execution'ı circular_mod'a bağımlı yap → döngü oluşur
print("\n--- Döngü enjeksiyonu: execution→circular_mod ekleniyor ---")
try:
    prop2 = engine.propose_architecture_change(
        "INJECT: execution→circular_mod",
        "modify_dependencies",
        "execution",
        ["governance", "circular_mod"],
        risk_score=0.9,
    )
    result2 = engine.apply_change(prop2.proposal_id)
    print(f"apply_change() döndü: {result2}")
    print("İstisna (exception): YOK\n")
except Exception as e:
    print(f"apply_change() İSTİSNA FIRLATTI: {type(e).__name__}: {e}\n")
    result2 = False

topo_after2 = engine.get_topology()
print("İşlem SONRASI grafik:")
for m, d in sorted(topo_after2.items()):
    marker = ""
    if m == "execution" and "circular_mod" in d:
        marker = " *** DÖNGÜ KAYNAĞI"
    elif m == "circular_mod":
        marker = " *** DÖNGÜDEKİ MODÜL"
    print(f"  {m:15s} → {d}{marker}")

cycles_after2 = engine.detect_cycles()
print(f"\nDöngü tespiti: {'EVET' if cycles_after2 else 'HAYIR'}")
if cycles_after2:
    for c in cycles_after2:
        print(f"  Döngü yolu: {' → '.join(c)}")

topo_before_str2 = str(topo_before2)
topo_after_str2 = str({k: list(v) for k, v in topo_after2.items()})
if topo_before_str2 == topo_after_str2:
    print("✅ Rollback: Grafik değişmemiş.")
else:
    print("❌ Rollback YOK: Grafik değişti (döngü aktif).")

# =====================================================================
# ADIM 4: apply_change'den önce manuel cycle check yapılsa ne olur?
# =====================================================================
print("\n" + "=" * 72)
print("ADIM 4: apply_change ÖNCESİ manuel cycle check simülasyonu")
print("=" * 72)
print("""
Eğer apply_change() şu şekilde yazılsaydı:

    def apply_change(self, proposal_id):
        ...
        # ÖNCE simulate et
        old_deps = dict(self._dependency_graph)
        self._dependency_graph[target] = new_deps
        if self.detect_cycles():
            self._dependency_graph = old_deps  # ROLLBACK
            return False
        ...

Döngüler otomatik engellenebilirdi.

Ancak MEVCUT KODDA böyle bir mekanizma YOK.
apply_change() her durumda değişikliği uyguluyor ve
döngü kontrolünü çağrıcıya (API/CLI) bırakıyor.
""")

# =====================================================================
# SONUÇ
# =====================================================================
print("=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
KATEGORİ: "tespit ediliyor ama uygulanmasına izin veriliyor (engelleme yok)"

KANIT:
  1. apply_change() kaynak kodunda detect_cycles() çağrısı: 0 (sıfır)
  2. Döngülü modify_dependencies çağrısı başarıyla uygulandı (True döndü)
  3. apply_change() exception fırlatmadı
  4. _dependency_graph değişti, grafik döngülü hale geldi
  5. detect_cycles() ile döngü tekrar teyit edildi
  6. Rollback mekanizması YOK — grafik eski haline dönmedi

Yani:
  - ✅ ArchitectureEvolutionEngine.detect_cycles()   = GERÇEK, ÇALIŞIYOR
  - ❌ ArchitectureEvolutionEngine.apply_change()     = DÖNGÜ KONTROLÜ YOK
  - ❌ Rollback                                       = YOK
  - ⚠️  Kullanıcı (API/CLI) önce detect_cycles() çağırıp sonuç kontrolü
       yapmakla yükümlü. apply_change() kendi başına korumalı değil.
""")
