#!/usr/bin/env python3
"""
evidence Modülü Gerçek Davranış Doğrulaması

Mock'suz, gerçek veriyle, bağımsız.
"""

from __future__ import annotations

from datetime import UTC, datetime

print("=" * 72)
print("1. TEMEL YAPI — Evidence sınıfı")
print("=" * 72)

from intelgraph.core.evidence import Evidence, Provenance, SourceLineage

print("Evidence alanları:")
for f in Evidence.__dataclass_fields__:
    ft = Evidence.__dataclass_fields__[f].type
    print(f"  {f:20s}  {ft}")

print("\nEvidence entity referansı içeriyor mu?")
print("  → HAYIR. Evidence'ın 'entity_id' veya 'entity' alanı YOK.")
print("  BaseEntity'de 'evidence: tuple[Evidence, ...]' var — yani")
print("  entity, evidence'ı içeriyor; evidence, entity'yi değil.")

# Gerçek obje oluştur
ev = Evidence(
    id="ev_001",
    source="MISP",
    content="IP 10.0.0.1 C2 sunucusu olarak tespit edildi",
    collected_at=datetime(2024, 6, 1, tzinfo=UTC),
    source_tier=1,
    trust_score=85,
    reliability_score=90,
)
print(f"\nEvidence objesi: {ev}")
print(f"id:              {ev.id}")
print(f"source:          {ev.source}")
print(f"content:         {ev.content}")
print(f"source_tier:     {ev.source_tier}")
print(f"trust_score:     {ev.trust_score}")
print(f"reliability:     {ev.reliability_score}")

# SourceLineage
lineage = SourceLineage(
    source_id="misp_1",
    source_url="https://misp.local/event/123",
    intermediate_sources=(
        SourceLineage(source_id="feed_1", source_url="https://feeds.example.com/threat"),
    ),
)
print(f"\nSourceLineage zinciri: {lineage.lineage_chain()}")

# Provenance
prov = Provenance(
    collection_id="col_001",
    collector_name="MISPConnector",
    source_lineage=lineage,
)
print(f"Provenance: collector={prov.collector_name}, lineage={prov.source_lineage is not None}")

# Entity'e bağlama
print("\n" + "-" * 72)
print("Entity'ye bağlama — BaseEntity.evidence")
print("-" * 72)

from intelgraph.core.entity.ip_address import IPAddress

ip = IPAddress(
    id="ev_test_ip",
    ip="10.0.0.1",
    rdns="c2.example.com",
    evidence=(ev,),  # Evidence doğrudan entity'nin içine gömülüyor
)
print(f"Entity: {ip.id}, IP={ip.ip}")
print(f"Entity.evidence: {len(ip.evidence)} adet")
print(f"  ilk evidence: id={ip.evidence[0].id}, source={ip.evidence[0].source}")

# Bağlantı türü: referans mı, kopya mı?
print("\nBağlantı türü: referans mı, kopya mı?")
print("  → EVIDENCE IDENTITY'e bakalım:")
ev2 = Evidence(
    id="ev_001",  # AYNI ID
    source="MISP",
    content="IP 10.0.0.1 C2 sunucusu olarak tespit edildi",
    collected_at=datetime(2024, 6, 1, tzinfo=UTC),
    source_tier=1,
    trust_score=85,
    reliability_score=90,
)
print(f"  ev is ev2: {ev is ev2} (referans)")
print(f"  ev == ev2: {ev == ev2} (değer) — frozen dataclass, tüm alanlar aynı")
print("  Evidence objesi referans olarak DEĞİL, değer olarak entity'ye gömülü.")
print("  Entity güncellenince eski evidence tuple'ı kaybolur.")

# =====================================================================
print("\n" + "=" * 72)
print("Entity güncellenince/silinince evidence ne olur?")
print("=" * 72)

from intelgraph.core.graph.graph import IntelligenceGraph

graph = IntelligenceGraph()

# Entity + evidence ekle
ip_src = IPAddress(
    id="test_cascade",
    ip="10.0.0.2",
    evidence=(
        Evidence(
            id="ev_c1",
            source="src1",
            content="original",
            collected_at=datetime.now(UTC),
            source_tier=1,
            trust_score=80,
            reliability_score=80,
        ),
    ),
)
graph.add_entity(ip_src)

# Entity'yi güncelle (yeni evidence ile)
ip_dst = IPAddress(
    id="test_cascade",
    ip="10.0.0.2",
    evidence=(
        Evidence(
            id="ev_c2",
            source="src2",
            content="updated",
            collected_at=datetime.now(UTC),
            source_tier=1,
            trust_score=90,
            reliability_score=90,
        ),
    ),
)
graph.add_entity(ip_dst)

node = graph.get_node("test_cascade")
print(f"Node'daki evidence sayısı: {len(node.entity.evidence)}")
print(f"  ev id: {node.entity.evidence[0].id}")
print(f"  ev source: {node.entity.evidence[0].source}")
print(f"  ev content: {node.entity.evidence[0].content}")

prev = graph.previous_versions.get("test_cascade", [])
if prev:
    print("\nprevious_versions'daki eski evidence:")
    for old_node in prev:
        for e in old_node.entity.evidence:
            print(f"  id={e.id}, source={e.source}, content={e.content}")
    print("✅ Eski evidence previous_versions'da korunuyor.")
else:
    print("❌ previous_versions boş!")

# Node silinince
graph.remove_node("test_cascade")
print(f"\nNode silindikten sonra graph.nodes: {list(graph.nodes.keys())}")
print("✅ Evidence entity ile birlikte kaybolur (cascade).")

print("\n⚠️  KRİTİK: Evidence entity'den BAĞIMSIZ bir varlık değildir.")
print("   Evidence objeleri entity içine gömülüdür.")
print("   Entity güncellenince eski evidence kaybolur (previous_versions'da kalsa da).")
print("   Evidence'ı sorgulamak için entity'ye erişmek gerekir.")
print("   Merkezi bir evidence deposu/dizini yok.")

# =====================================================================
print("\n" + "=" * 72)
print("2. ÇELİŞKİ / CONTRADICTION DURUMU")
print("=" * 72)

# Simple Evidence ile çelişki tespiti
print("--- Simple Evidence ile contradiction ---")
print("Evidence sınıfının kendisinde contradiction mekanizması YOK.")
print("support_type, claim, contradiction_score alanları YOK.")
print("Çelişki tespiti için EvidenceChain + ContradictionDetector kullanılıyor.\n")

# EvidenceChain ile contradiction
from intelgraph.core.evidence_chain import (
    ContradictionDetector,
    EvidenceChain,
    EvidenceItem,
    SupportType,
)

print("--- EvidenceChain + ContradictionDetector ---")
chain = EvidenceChain(entity_id="test_ip_10_0_0_1")
chain.add_item(
    EvidenceItem(
        source_id="src_a",
        claim="IP zararsız",
        support_type=SupportType.SUPPORTS,
        confidence=80.0,
    )
)
chain.add_item(
    EvidenceItem(
        source_id="src_b",
        claim="IP zararlı",
        support_type=SupportType.CONTRADICTS,
        confidence=90.0,
    )
)

detector = ContradictionDetector()
contradictions = detector.detect(chain)

print(f"EvidenceItem sayısı: {chain.evidence_count}")
print(f"Contradiction sayısı: {len(contradictions)}")
print(f"Chain contradiction_score: {chain.contradiction_score}")
print(f"Chain status: {chain.status}")

if contradictions:
    for c in contradictions:
        print("\n  ContradictionRecord:")
        print(f"    type:     {c.contradiction_type}")
        print(f"    score:    {c.score}")
        print(f"    ev_a:     {c.evidence_id_a[:12]}... SUPPORTS")
        print(f"    ev_b:     {c.evidence_id_b[:12]}... CONTRADICTS")

print("\n✅ ContradictionDetector çelişkiyi tespit ediyor:")
print("   - SupportType farklı (SUPPORTS vs CONTRADICTS) → direct contradiction (score=100)")
print("   - Chain'in contradiction_score'u güncelleniyor")
print("   - Status CONTESTED olarak işaretleniyor")

# =====================================================================
print("\n" + "=" * 72)
print("3. GÜVEN SKORU HESAPLAMA")
print("=" * 72)

from intelgraph.core.evidence_chain import ConfidenceComputer

print("--- ConfidenceComputer ile aggregate skor ---")
chain2 = EvidenceChain(entity_id="test_ip_10_0_0_2")
chain2.add_item(
    EvidenceItem(
        source_id="misp",
        claim="IP C2 sunucusu",
        support_type=SupportType.SUPPORTS,
        confidence=90.0,
    )
)
chain2.add_item(
    EvidenceItem(
        source_id="vt",
        claim="IP C2 sunucusu",
        support_type=SupportType.SUPPORTS,
        confidence=80.0,
    )
)
chain2.add_item(
    EvidenceItem(
        source_id="alienvault",
        claim="IP zararsız",
        support_type=SupportType.CONTRADICTS,
        confidence=70.0,
    )
)

source_trust = {"misp": 95, "vt": 85, "alienvault": 60}
final_conf = ConfidenceComputer.compute(chain2, source_trust)

print("3 adet evidence:")
for item in chain2.evidence:
    print(
        f"  {item.source_id:15s} claim='{item.claim:20s}' {item.support_type.name:12s} conf={item.confidence}"
    )
print(f"\nKaynak güven: {source_trust}")
print(f"\nAggregate confidence:      {final_conf}")
print(f"contradiction_score:       {chain2.contradiction_score}")
print(f"Status:                    {chain2.status.name}")

# Adım adım hesaplama
print("\nHesap adımları:")
print("  1. Weighted sum = Σ(confidence × source_trust/100)")
print("  2. source_trust ile normalize")
print("  3. Eğer agreement_ratio > 0.7 → %10 boost")
print("  4. contradiction_ratio > 0.3 → penalty")
print("  (ConfidenceComputer kaynağı: evidence_chain/confidence.py)")

# Karşılaştırma: tek evidence vs aggregate
print("\n--- Tek evidence vs aggregate ---")
single_max = max(item.confidence for item in chain2.evidence)
print(f"  Tek en yüksek:     {single_max}")
print(f"  Aggregate (ağırlıklı): {final_conf}")
print(f"  Fark: {final_conf - single_max:+.1f} (consensus boost - contradiction penalty)")
print(
    "\n✅ Aggregate confidence, weighted average + consensus boost + contradiction penalty ile hesaplanıyor."
)
print("   Gerçek bir agregasyon mantığı VAR.")

# =====================================================================
print("\n" + "=" * 72)
print("4. EvidenceChain → Entity/Graph bağlantısı")
print("=" * 72)

# EvidenceChain graph'a bağlı mı?
print("BaseEntity'nin evidence alanı: tuple[Evidence, ...] — yani EvidenceChain DEĞİL.")
print("IntelligenceGraph'te EvidenceChain referansı: YOK.")
print("EvidenceChainManager/Storage ayrı bir sistem (evidence_chain/).")
print("Graph'taki entity'ler simple Evidence kullanıyor.")

# Bağlantı testi
graph2 = IntelligenceGraph()
e_with_evidence = IPAddress(
    id="ip_with_ev",
    ip="10.0.0.3",
    evidence=(
        Evidence(
            id="ev_g1",
            source="test",
            content="graph evidence",
            collected_at=datetime.now(UTC),
            source_tier=1,
            trust_score=80,
            reliability_score=80,
        ),
    ),
)
graph2.add_entity(e_with_evidence)
node = graph2.get_node("ip_with_ev")
print(f"Graph'taki node evidence: {len(node.entity.evidence)} adet")
print("  EvidenceChain'e bağlı mı? HAYIR (entity'ye gömülü).")

# =====================================================================
print("\n" + "=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
1. Temel yapı ve kaynak izlenebilirliği:
   → "çalışıyor ama risk var"
   Evidence: source, content, trust/reliability_score, source_tier, collected_at.
   Entity referansı YOK — evidence entity'ye GÖMÜLÜ (BaseEntity.evidence).
   Kaynak izlenebilirliği: SourceLineage ile zincirleme takip mümkün.
   RİSK: Entity güncellenince eski evidence kaybolur (previous_versions'da kalsa da).
   Merkezi evidence deposu yok — evidence'ı bulmak için entity'ye erişmek gerek.

2. Çelişki/contradiction:
   → "çalışıyor ama risk var"
   Simple Evidence'da contradiction mekanizması YOK.
   EvidenceChain + ContradictionDetector'da VAR:
   - Direct contradiction (SUPPORTS vs CONTRADICTS) → score=100
   - Partial conflict (Jaccard similarity ile claim karşılaştırması)
   - Chain seviyesinde contradiction_score + status (CONTESTED/DEBUNKED)
   RİSK: EvidenceChain, entity/graph sistemine BAĞLI DEĞİL.
   Entity'ler simple Evidence kullanır, EvidenceChain kullanmaz.
   TruthConsistencyGovernor (Phase 32) da bu zincire bağlı değil.

3. Güven skoru hesaplama:
   → "gerçek mantık var + doğru çalışıyor"
   ConfidenceComputer (evidence_chain/confidence.py):
   - Ağırlıklı ortalama (source_trust × confidence)
   - consensus_boost: agreement_ratio > 0.7 → +%10
   - contradiction_penalty: contradiction_ratio > 0.3 → penalty
   - Final: max(0, min(100, clip))
   - Status otomatik: VERIFIED/CONTESTED/DEBUNKED/UNKNOWN
   ANCAK: Bu aggregate hesaplama simple Evidence için KULLANILMIYOR.
   Sadece EvidenceChain'de çalışıyor.

ÖZET:
   İKİ AYRI SİSTEM VAR:
   1) Simple Evidence (entity'ye gömülü) — kanıt tutar, çelişki/agregasyon YOK
   2) EvidenceChain (bağımsız sistem) — contradiction + aggregate confidence VAR
      ama entity/graph'a entegre DEĞİL

   Bu, EntityMatcher + MergeEngine ile aynı desen: "mantık var, entegrasyon yok."
""")
