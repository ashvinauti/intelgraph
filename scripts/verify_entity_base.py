#!/usr/bin/env python3
"""
entity.base Gerçek Davranış Doğrulaması

Mock'suz, gerçek veriyle, bağımsız.
"""

from __future__ import annotations

import copy
import inspect
import json
from dataclasses import FrozenInstanceError, fields

from intelgraph.core.entity import (
    BaseEntity,
    Certificate,
    Company,
    Domain,
    Email,
    EntityType,
    IPAddress,
    Person,
    Technology,
    Username,
)

print("=" * 72)
print("1. TEMEL SINIF DAVRANIŞI")
print("=" * 72)

# =====================================================================
# 1a. Farklı alt sınıflardan obje oluşturma
# =====================================================================
print("-" * 72)
print("1a. Farklı alt sınıflardan gerçek obje oluşturma")
print("-" * 72)

ip = IPAddress(
    ip="10.0.0.1",
    rdns="host.example.com",
    asn="AS15169",
    organization="Example Inc",
    open_ports=(22, 80, 443),
)
domain = Domain(
    domain_name="example.com",
    registrant="John Doe",
    registrar="GoDaddy",
    nameservers=("ns1.example.com",),
)
person = Person(
    name="Alice",
    email_addresses=("alice@example.com",),
    title="Analyst",
    company_affiliations=("Example Inc",),
)
company = Company(name="Example Inc", domain="example.com", industry="Technology")

print(f"IPAddress:    id={ip.id[:12]}... type={ip.entity_type} ip={ip.ip}")
print(f"Domain:       id={domain.id[:12]}... type={domain.entity_type} domain={domain.domain_name}")
print(f"Person:       id={person.id[:12]}... type={person.entity_type} name={person.name}")
print(f"Company:      id={company.id[:12]}... type={company.entity_type} name={company.name}")

assert isinstance(ip, BaseEntity)
assert isinstance(domain, BaseEntity)
assert isinstance(person, BaseEntity)
assert isinstance(company, BaseEntity)
assert ip.entity_type == EntityType.IP_ADDRESS
assert domain.entity_type == EntityType.DOMAIN
assert person.entity_type == EntityType.PERSON
assert company.entity_type == EntityType.COMPANY
print("✅ 4 farklı alt sınıf BaseEntity'den türüyor, entity_type doğru atanmış.")

# =====================================================================
# 1b. Validasyon — IPAddress'e geçersiz IP
# =====================================================================
print("\n" + "-" * 72)
print("1b. Validasyon — geçersiz değerler")
print("-" * 72)

# IP validation: IPAddress sadece str alıyor, validasyon yok
bad_ip = IPAddress(ip="999.999.999.999")
print(f"Geçersiz IP (999.999.999.999): ip={bad_ip.ip}")
print("  → KABUL EDİLDİ — IPAddress'te IP format validasyonu YOK.")
print("  BaseEntity sadece confidence_score (0-100) ve trust_score (0-100) kontrol ediyor.")

# Confidence score validasyonu
try:
    IPAddress(ip="1.1.1.1", confidence_score=150)
    raise AssertionError("Bu hataya düşmemeli!")
except ValueError as e:
    print(f"confidence_score=150: ValueError ✓ — {e}")

try:
    IPAddress(ip="1.1.1.1", trust_score=-5)
    raise AssertionError("Bu hataya düşmemeli!")
except ValueError as e:
    print(f"trust_score=-5:      ValueError ✓ — {e}")

# __post_init__ kontrolü
src = inspect.getsource(BaseEntity.__post_init__)
print(f"\nBaseEntity.__post_init__:\n{src}")

# Diğer alt sınıflarda ek validasyon var mı?
for cls in [IPAddress, Domain, Person, Company, Email, Username, Technology, Certificate]:
    if hasattr(cls, "__post_init__") and cls.__post_init__ is not BaseEntity.__post_init__:
        print(f"  {cls.__name__} EK __post_init__ var!")
    else:
        print(f"  {cls.__name__}: ek validasyon yok (BaseEntity'inkini kullanıyor)")

print("\n✅ BaseEntity: sadece confidence/trust score (0-100) validasyonu var.")
print("⚠️  Alt sınıflarda alan bazlı validasyon (IP formatı, email formatı vb.) YOK.")

# =====================================================================
# 1c. Frozen — immutable mı?
# =====================================================================
print("\n" + "-" * 72)
print("1c. Frozen — gerçekten immutable mı?")
print("-" * 72)

try:
    ip.ip = "1.2.3.4"
    print("❌ Frozen değil! Mutasyon mümkün.")
except FrozenInstanceError:
    print("ip.ip = '1.2.3.4' → FrozenInstanceError ✓ (immutable)")
try:
    ip.entity_type = EntityType.DOMAIN
    print("❌ entity_type değiştirilebildi!")
except FrozenInstanceError:
    print("entity_type da immutable ✓")
print("✅ BaseEntity ve tüm alt sınıfları frozen = immutable.")

# =====================================================================
print("\n" + "=" * 72)
print("2. EŞİTLİK VE KİMLİK MANTIĞI")
print("=" * 72)

# =====================================================================
# 2a. Aynı veri = aynı obje mi?
# =====================================================================
print("-" * 72)
print("2a. Aynı veriyle iki obje == eşit mi?")
print("-" * 72)

a1 = IPAddress(ip="10.0.0.1", rdns="test.example.com")
a2 = IPAddress(ip="10.0.0.1", rdns="test.example.com")
a3 = a1  # aynı referans

print(f"a1 == a2 (farklı instance, aynı veri): {a1 == a2}")
print(f"a1 is a2 (aynı referans?):              {a1 is a2}")
print(f"a1 == a3 (aynı referans):               {a1 == a3}")
print(f"a1.id == a2.id? {a1.id == a2.id}")
print(f"a1.ip == a2.ip? {a1.ip == a2.ip}")

# Frozen dataclass default __eq__ tüm alanları karşılaştırır
# id farklı olduğu için eşit olmamalı
assert a1 != a2, "ID'ler farklı olduğu için != olmalı!"
assert a1 is a3
print("✅ İki farklı instance asla == değil — çünkü ID'ler farklı.")

# Aynı ID verilirse?
# created_at/updated_at default_factory olduğu için her seferinde farklı timestamp alırız
# Bu yüzden aynı ID + aynı veriyle bile objeler eşit olmaz (çünkü timestamp'ler farklı)
# Test etmek için aynı timestamp'leri kullanmalıyız
from datetime import UTC, datetime

fixed_ts = datetime(2025, 1, 1, tzinfo=UTC)
a4 = IPAddress(
    id=a1.id, ip="10.0.0.1", rdns="test.example.com", created_at=fixed_ts, updated_at=fixed_ts
)
a4b = IPAddress(
    id=a1.id, ip="10.0.0.1", rdns="test.example.com", created_at=fixed_ts, updated_at=fixed_ts
)
a1_with_fixed_ts = IPAddress(
    id=a1.id, ip="10.0.0.1", rdns="test.example.com", created_at=fixed_ts, updated_at=fixed_ts
)
print(f"\na4 == a4b (aynı ID + aynı veri + aynı timestamp): {a4 == a4b}")
assert a4 == a4b, "Her şey aynıysa eşit olmalı!"
print("✅ Aynı ID + aynı field'lar + aynı timestamp == True.")

a5 = IPAddress(
    id=a1.id, ip="10.0.0.2", rdns="other.example.com", created_at=fixed_ts, updated_at=fixed_ts
)
print(f"a4 == a5 (aynı ID, farklı veri, aynı timestamp): {a4 == a5}")
assert a4 != a5, "Aynı ID ama farklı field'lar != olmalı!"
print("✅ Aynı ID ama farklı field'lar == False.")

# KRİTİK: created_at default_factory nedeniyle pratikte iki obje asla == olamaz
print("\n⚠️  KRİTİK: created_at/updated_at default_factory olduğu için")
print("   pratikte hiçbir iki farklı instance == eşit değildir.")
print("   created_at/updated_at aynı olsa bile, id ULID olduğu için farklıdır.")
print("   Bu tasarım: entity'ler unique olacak şekilde bilinçli yapılmış.")

# =====================================================================
# 2b. ID üretimi — deterministik mi?
# =====================================================================
print("\n" + "-" * 72)
print("2b. ID üretimi — deterministik mi (aynı veriden aynı ID)?")
print("-" * 72)

# BaseEntity._generate_id = str(ulid.new())
# ULID: timestamp + random — her zaman farklı
print("_generate_id: str(ulid.new()) — entity/base.py:27")
print("  ULID: timestamp (48-bit) + random (80-bit) — her çağrıda farklı ID")
ids = set()
for _ in range(100):
    ids.add(IPAddress(ip="10.0.0.1").id)
print("\n100 tane IPAddress(ip='10.0.0.1') üretildi.")
print(f"Benzersiz ID sayısı: {len(ids)}")
print(f"Hiç duplicate var mı? {'HAYIR' if len(ids) == 100 else 'EVET'}")
assert len(ids) == 100, "ULID her seferinde farklı olmalı!"

print("\n⚠️  KRİTİK: ID'ler ULID tabanlı (timestamp + random).")
print("   Aynı IP/Domain/Kişi her eklendiğinde FARKLI ID alır.")
print("   Bu demektir ki: graph.add_entity()'deki duplicate detection")
print("   aynı gerçek varlık için ASLA TETİKLENMEZ —")
print("   çünkü her obje farklı ID ile gelir.")
print("   Bu bilinçli bir tasarım mı yoksa boşluk mu?")
print("   (EntityMatcher + MergeEngine Phase 22'de bunu ele alıyor olabilir.)")

# =====================================================================
# 2c. Hash edilebilir mi? (set/dict anahtarı olarak)
# =====================================================================
print("\n" + "-" * 72)
print("2c. Hash edilebilir mi (set/dict anahtarı)?")
print("-" * 72)

try:
    s = {ip, domain, person}
    print(f"Set'e eklendi: {len(s)} eleman")
    print("✅ Frozen olduğu için hashable.")
except TypeError as e:
    print(f"❌ Hashable DEĞİL: {e}")

# =====================================================================
print("\n" + "=" * 72)
print("3. SERİLEŞTİRME (Serialization)")
print("=" * 72)

# =====================================================================
# 3a. to_dict / from_dict var mı?
# =====================================================================
print("-" * 72)
print("3a. BaseEntity'de to_dict/from_dict metodu var mı?")
print("-" * 72)

for method_name in ["to_dict", "from_dict", "to_json", "from_json", "asdict"]:
    has = hasattr(BaseEntity, method_name) or any(
        hasattr(cls, method_name) for cls in [IPAddress, Domain, Person, Company]
    )
    print(f"  {method_name}: {'VAR' if has else 'YOK'}")

# dataclasses.fields ile tüm alanları alabiliriz
print("\nIPAddress alanları (BaseEntity + kendisi):")
for f in fields(IPAddress):
    inherited = f.name in {ff.name for ff in fields(BaseEntity)}
    print(
        f"  {f.name:20s} type={f.type.__name__:15s} default={f.default!r:30s} {'(inherited)' if inherited else ''}"
    )

# =====================================================================
# 3b. Manuel round-trip — dict → entity
# =====================================================================
print("\n" + "-" * 72)
print("3b. Manuel round-trip: entity → dict → yeni entity")
print("-" * 72)

ip_orig = IPAddress(
    id="test_roundtrip",
    ip="192.168.1.1",
    rdns="router.local",
    asn="AS12345",
    organization="Test Corp",
    open_ports=(22, 443, 8080),
    confidence_score=85,
    trust_score=75,
    aliases=("gateway", "main-router"),
)

# Entity → dict (sadece init=True olan alanlar)

ip_dict = {
    f.name: getattr(ip_orig, f.name)
    for f in fields(IPAddress)
    if f.init  # exclude init=False (entity_type)
}
# Convert sets to tuples if needed (for serialization)
for k, v in ip_dict.items():
    if isinstance(v, (set, list)):
        ip_dict[k] = tuple(v)

print("Entity'den alınan dict (init=True alanlar):")
for k, v in sorted(ip_dict.items()):
    print(f"  {k:20s} = {v!r}")

# Dict → yeni entity
ip_restored = IPAddress(**ip_dict)

print(f"\nOrijinal entity:   {ip_orig}")
print(f"Geri yüklenen:      {ip_restored}")
print(f"Eşit mi?            {ip_orig == ip_restored}")

assert ip_orig == ip_restored, "Round-trip veri kaybı olmamalı!"
assert ip_orig.ip == ip_restored.ip
assert ip_orig.open_ports == ip_restored.open_ports
print("✅ Round-trip başarılı — tüm alanlar korunuyor.")

# =====================================================================
# 3c. JSON serileştirme
# =====================================================================
print("\n" + "-" * 72)
print("3c. JSON serileştirme")
print("-" * 72)

# datetime alanları JSON'a çevrilemez — özel encoder gerek
# init=False alanlar (entity_type) constructor'a geçilemez
json_safe_dict = {k: v for k, v in ip_dict.items() if k != "entity_type"}
try:
    json_str = json.dumps(json_safe_dict, default=str)
    print(f"JSON (datetime'lar str'e çevrildi): {json_str[:120]}...")
    print("✅ JSON serileştirme mümkün (default=str ile).")
except Exception as e:
    print(f"❌ JSON hatası: {e}")

# JSON'dan geri yükleme — entity_type haricindeki alanlarla
json_loaded = json.loads(json_str)
# datetime string'leri geri datetime'a çevir (manuel)
json_loaded["created_at"] = datetime.fromisoformat(json_loaded["created_at"])
json_loaded["updated_at"] = datetime.fromisoformat(json_loaded["updated_at"])
json_loaded["open_ports"] = tuple(json_loaded["open_ports"])
json_loaded["aliases"] = tuple(json_loaded["aliases"])
json_loaded["evidence"] = tuple(json_loaded["evidence"])
json_loaded["provenance"] = tuple(json_loaded["provenance"])

ip_restored2 = IPAddress(**json_loaded)
print(
    f"Tip doğru mu? {type(ip_restored2).__name__} == IPAddress, entity_type={ip_restored2.entity_type}"
)
assert isinstance(ip_restored2, IPAddress)
assert ip_restored2.entity_type == EntityType.IP_ADDRESS
assert ip_restored2.ip == "192.168.1.1"
assert ip_restored2.open_ports == (22, 443, 8080)
print("✅ JSON round-trip başarılı — entity_type otomatik atandı (init=False).")

# =====================================================================
# 3d. Deep copy
# =====================================================================
print("\n" + "-" * 72)
print("3d. Deep copy — frozen olduğu için copy vs referans")
print("-" * 72)

ip_copy = copy.deepcopy(ip_orig)
print(f"Deep copy eşit mi?  {ip_orig == ip_copy}")
print(f"Deep copy aynı mı?  {ip_orig is ip_copy}")
assert ip_orig == ip_copy
assert ip_orig is not ip_copy
print("✅ Deep copy çalışıyor.")

# =====================================================================
print("\n" + "=" * 72)
print("SONUÇ RAPORU")
print("=" * 72)

print("""
1a. Farklı alt sınıflar:
    → "gerçek mantık var + doğru çalışıyor"
    8 alt sınıf (IPAddress, Domain, Person, Company, Email, Username,
    Technology, Certificate) BaseEntity'den türüyor. entity_type otomatik atanıyor.

1b. Validasyon:
    → "çalışıyor ama risk var"
    SADECE confidence_score (0-100) ve trust_score (0-100) kontrol ediliyor
    (BaseEntity.__post_init__). Alan bazlı validasyon YOK — IPAddress'e
    "999.999.999.999" yazılabilir. Bu bilinçli bir esneklik mi yoksa
    eksik mi olduğu tartışılır, ancak hiçbir alt sınıfta domain formatı,
    email formatı, IP formatı kontrolü yok.

1c. Immutability:
    → "gerçek mantık var + doğru çalışıyor"
    FrozenInstanceError ile tam koruma. Hashable.

2a. Eşitlik:
    → "gerçek mantık var + doğru çalışıyor"
    Frozen dataclass default __eq__: tüm alanları karşılaştırır.
    ID farklıysa !=, aynı ID + aynı veri ==.

2b. ID üretimi:
    → "çalışıyor ama risk var"
    ULID tabanlı (timestamp + random) — her obje benzersiz ID alır.
    Aynı gerçek varlık (örn: aynı IP) tekrar eklenince FARKLI ID alır.
    graph'daki duplicate detection (yeni düzeltme) bu durumda
    ÇALIŞMAZ — çünkü ID'ler zaten farklı.
    Bu bir "entity resolution" sorunu — Phase 22 EntityMatcher
    ve MergeEngine'in görevi.

3. Serileştirme:
    → "çalışıyor ama resmi API yok"
    to_dict()/from_dict() metodu YOK.
    dataclasses.fields() ile manuel dict dönüşümü mümkün.
    Round-trip başarılı. JSON default=str ile çalışıyor.
    entity_type enum olarak korunuyor (int değil).
""")
