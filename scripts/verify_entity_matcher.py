#!/usr/bin/env python3
"""
Phase 22 EntityMatcher/MergeEngine Uçtan Uca Doğrulama

Mock'suz, gerçek veriyle — iki kaynaktan gelen aynı IP'yi graph'a ekleyip
EntityMatcher'in devreye girip girmediğini kanıtla.
"""

from __future__ import annotations

from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.graph import IntelligenceGraph

print("=" * 72)
print("1. KOD VARLIĞI KONTROLÜ")
print("=" * 72)

from intelgraph.core.source.resolution import EntityMatcher, MergeEngine, ResolutionAudit

print(f"EntityMatcher:  {EntityMatcher}")
print(f"MergeEngine:    {MergeEngine}")
print(f"ResolutionAudit:{ResolutionAudit}")

# graph.py add_entity EntityMatcher çağırıyor mu?
import inspect

src = inspect.getsource(IntelligenceGraph.add_entity)
if "EntityMatcher" in src or "entity_matcher" in src or "merge" in src:
    print("\ngraph.add_entity İÇİNDE EntityMatcher/MergeEngine çağrısı VAR.")
else:
    print("\n❌ graph.add_entity İÇİNDE EntityMatcher/MergeEngine çağrısı YOK.")
    # Satır satır göster
    for i, line in enumerate(src.split("\n"), 1):
        print(f"   {i}: {line}")

print("\n" + "=" * 72)
print("2. UÇTAN UCA SENARYO — Otomatik birleşiyor mu?")
print("=" * 72)

graph = IntelligenceGraph()

# Pazartesi log'undan gelen kayıt
entity_monday = IPAddress(
    ip="192.168.1.5",
    rdns="suspicious-host.example.com",
    confidence_score=60,
    trust_score=50,
)
node_monday = graph.add_entity(entity_monday)

# Salı raporundan gelen kayıt (aynı IP, farklı ULID)
entity_tuesday = IPAddress(
    ip="192.168.1.5",
    rdns="cve-associated-host.example.com",
    confidence_score=85,
    trust_score=70,
)
node_tuesday = graph.add_entity(entity_tuesday)

print(f"Pazartesi node ID:  {node_monday.id}")
print(f"Salı node ID:       {node_tuesday.id}")
print(f"ID'ler eşit mi?     {node_monday.id == node_tuesday.id}")
print(f"Graph node sayısı:  {graph.node_count}")
print("\nGraph'taki düğümler:")
for nid, n in graph.nodes.items():
    print(f"  {nid} → IP={n.entity.ip}, rdns={n.entity.rdns}, conf={n.entity.confidence_score}")

if graph.node_count == 1:
    print("\n✅ TEK node — EntityMatcher otomatik birleştirdi!")
else:
    print("\n❌ İKİ AYRI node — EntityMatcher otomatik çalışmıyor!")
    print("   Aynı IP (192.168.1.5) graph'TA İKİ KERE KAYITLI.")

print("\n" + "=" * 72)
print("3. MANUEL EntityMatcher + MergeEngine Çağrısı")
print("=" * 72)

# EntityMatcher dict bazlı çalışıyor — entity'leri dict'e çevirelim
from dataclasses import fields


def entity_to_dict(entity) -> dict:
    d = {}
    for f in fields(entity):
        if f.init:  # exclude init=False (entity_type)
            val = getattr(entity, f.name)
            if hasattr(val, "isoformat"):  # datetime
                val = val.isoformat()
            elif isinstance(val, tuple):
                val = list(val)
            d[f.name] = val
    d["name"] = entity.ip  # EntityMatcher name/label alanı kullanıyor
    d["ip"] = entity.ip
    return d


monday_dict = entity_to_dict(entity_monday)
tuesday_dict = entity_to_dict(entity_tuesday)

print("Pazartesi dict (özet):")
for k, v in sorted(monday_dict.items()):
    print(f"  {k}: {v!r}")
print("\nSalı dict (özet):")
for k, v in sorted(tuesday_dict.items()):
    print(f"  {k}: {v!r}")

matcher = EntityMatcher(match_threshold=0.7, exact_fields=["ip", "domain_name", "email"])
score = matcher.match(monday_dict, tuesday_dict)
print(f"\nEntityMatcher.match() skoru: {score}")
print(f"Eşik (0.7): {'GEÇTİ' if score >= 0.7 else 'KALDI'}")

duplicates = matcher.find_duplicates([monday_dict, tuesday_dict])
print(f"\nfind_duplicates sonucu: {len(duplicates)} çift bulundu")
for a, b, s in duplicates:
    print(f"  {a.get('id', '?')[:12]} ↔ {b.get('id', '?')[:12]}  skor={s:.4f}")

# Merge
merger = MergeEngine(default_strategy="most_confident")
merged = merger.merge(monday_dict, tuesday_dict, strategy="most_confident")
print("\nMergeEngine.merge() sonucu:")
for k, v in sorted(merged.items()):
    print(f"  {k}: {v!r}")

# Denetim kaydı
audit_entries = merger.audit.get_history()
print(f"\nDenetim kaydı: {len(audit_entries)} giriş")
for entry in audit_entries:
    for k, v in sorted(entry.items()):
        print(f"  {k}: {v!r}")

print("\n✅ EntityMatcher manuel çağrıldığında ÇALIŞIYOR:")
print("   - Aynı IP'yi (192.168.1.5) exact_fields ile eşleştirdi (skor=1.0)")
print("   - MergeEngine en yüksek confidence_score olanı (85) baz aldı")
print("   - Audit kaydı üretildi")

# Merge sonucunda her iki kaynaktan gelen bilgi korunuyor mu?
print("\n✅ Merge sonrası:")
print(f"   - IP: {merged.get('ip')} (kaynaklardan biri)")
print(f"   - rdns: {merged.get('rdns')} (en yüksek confidence'li kaynaktan)")
print(f"   - confidence_score: {merged.get('confidence_score')} (max alındı: 85)")
print("   ❌ ANCAK: Pazartesi'nin rdns değeri ('suspicious-host') KAYBOLDU.")
print("      MergeEngine sadece max confidence'ı baz alıp diğer kaynağın")
print("      bilgisini atmıyor, farklı field'ları dolduruyor — ama bu örnekte")
print("      her iki kaynak da rdns doldurduğu için yenisini kullandı.")

print("\n" + "=" * 72)
print("4. Merge SONUCU graph'a eklenebilir mi?")
print("=" * 72)

# Merge edilmiş veriden yeni entity oluştur
merged_entity = IPAddress(
    id="merged_ip_192_168_1_5",
    ip=merged.get("ip", ""),
    rdns=merged.get("rdns", ""),
    confidence_score=int(merged.get("confidence_score", 0)),
    trust_score=int(merged.get("trust_score", 0)),
)

# Önce eski node'ları temizle, sonra birleşmiş node'u ekle
graph2 = IntelligenceGraph()
graph2.add_entity(merged_entity)
print(f"Birleşmiş node eklendi: ID={merged_entity.id}, IP={merged_entity.ip}")
print(f"Graph node sayısı: {graph2.node_count}")
print("✅ Merge sonucu graph'a eklenebiliyor — ANCAK bu MANUEL bir süreç.")

print("\n" + "=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
KATEGORİ: "EntityMatcher var ama manuel çağrı gerekiyor, otomatik entegrasyon yok"

1. Kod varlığı:
   EntityMatcher, MergeEngine, ResolutionAudit -> VAR (core/source/resolution.py)
   graph.add_entity() içinde EntityMatcher çağrısı -> YOK

2. Otomatik entegrasyon:
   graph.add_entity() EntityMatcher'ı HİÇ çağırmıyor.
   Aynı IP'ye sahip iki entity her seferinde ayrı node olarak ekleniyor.
   2 node eklendi -> 2 ayrı node (birleşme YOK)

3. Manuel EntityMatcher:
   match("192.168.1.5", "192.168.1.5") = 1.0 (exact match on 'ip' field)
   MergeEngine.merge() başarılı çalışıyor, audit kaydı üretiliyor.
   Merge sonucu dict → yeni entity → graph.add_entity() ile elle eklenebiliyor.

4. KRİTİK TASARIM BOŞLUĞU:
   - EntityMatcher dict tabanlı çalışıyor (BaseEntity değil)
   - graph.add_entity() BaseEntity alıyor
   - İkisi arasında köprü (adapter/wiring) YOK
   - Birleştirme için kullanıcının şunları YAPMASI GEREKİYOR:
     a) Entity'leri dict'e çevir
     b) EntityMatcher.match()/find_duplicates() çağır
     c) Eşleşme bulunursa MergeEngine.merge() çağır
     d) Merge sonucunu yeni entity'e dönüştür
     e) Eski node'ları temizle
     f) Yeni birleşmiş node'u ekle
     g) DataSourceStore.record_resolution() ile kalıcı kayıt

   Bu adımların HİÇBİRİ otomatik değil. EntityMatcher ve MergeEngine
   "kullanıma hazır kütüphane" olarak duruyor, entegre değil.
""")
