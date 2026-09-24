from datetime import datetime
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.evidence import Provenance
from intelgraph.core.relationship import Relationship


def _entity_to_dict(entity: BaseEntity) -> dict[str, Any]:
    data = {
        "id": entity.id,
        "version": entity.version,
        "entity_type": entity.entity_type.type_name,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
        "aliases": list(entity.aliases),
        "confidence_score": entity.confidence_score,
        "trust_score": entity.trust_score,
    }
    for field in (
        "name",
        "legal_name",
        "domain",
        "domain_name",
        "address",
        "username",
        "platform",
        "profile_url",
        "ip",
        "rdns",
        "asn",
        "organization",
        "title",
        "industry",
        "headquarters",
        "registrant",
        "registrar",
        "serial",
        "issuer",
        "subject",
        "fingerprint",
        "category",
        "version",
        "cpe",
        "email_addresses",
        "usernames",
        "social_profiles",
        "company_affiliations",
        "domains",
        "phone_numbers",
        "subsidiaries",
        "nameservers",
        "ip_addresses",
        "technologies",
        "associated_accounts",
        "open_ports",
        "creation_date",
        "expiration_date",
        "validity_start",
        "validity_end",
    ):
        val = getattr(entity, field, None)
        if val is not None and val != "" and val != () and val != ():
            if isinstance(val, (list, tuple)):
                data[field] = list(val)
            elif hasattr(val, "isoformat"):
                data[field] = val.isoformat()
            else:
                data[field] = val
    return data


def _dict_to_entity(data: dict[str, Any], entity_type: str) -> BaseEntity:
    from intelgraph.core.entity import (
        Certificate,
        Company,
        Domain,
        Email,
        IPAddress,
        Person,
        Technology,
        Username,
    )

    mapping = {
        "person": Person,
        "company": Company,
        "domain": Domain,
        "email": Email,
        "username": Username,
        "ip_address": IPAddress,
        "technology": Technology,
        "certificate": Certificate,
    }
    cls = mapping.get(entity_type)
    if cls is None:
        raise ValueError(f"Unknown entity type: {entity_type}")
    field_map = {
        "email_addresses": tuple,
        "usernames": tuple,
        "social_profiles": tuple,
        "company_affiliations": tuple,
        "domains": tuple,
        "phone_numbers": tuple,
        "subsidiaries": tuple,
        "nameservers": tuple,
        "ip_addresses": tuple,
        "technologies": tuple,
        "associated_accounts": tuple,
        "open_ports": tuple,
        "aliases": tuple,
    }
    kwargs: dict[str, Any] = {}
    for key, val in data.items():
        if key in field_map and isinstance(val, list):
            kwargs[key] = field_map[key](val)
        elif key in ("creation_date", "expiration_date", "validity_start", "validity_end") and val:
            kwargs[key] = datetime.fromisoformat(val)
        elif key == "id":
            kwargs[key] = val
        elif key in ("version", "confidence_score", "trust_score"):
            kwargs[key] = val
        elif key == "entity_type":
            continue
        elif key in ("created_at", "updated_at") and val:
            kwargs[key] = datetime.fromisoformat(val)
        else:
            kwargs[key] = val
    return cls(**kwargs)


def _relationship_to_dict(rel: Relationship) -> dict[str, Any]:
    return {
        "id": rel.id,
        "type": rel.type.type_name,
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "version": rel.version,
        "confidence_score": rel.confidence_score,
        "trust_weight": rel.trust_weight,
        "created_at": rel.created_at.isoformat(),
    }


def _dict_to_relationship(data: dict[str, Any], rel_type: str) -> Relationship:
    from intelgraph.core.relationship import RelationshipType

    rtype = RelationshipType[rel_type.upper()]
    return Relationship(
        id=data["id"],
        type=rtype,
        source_id=data["source_id"],
        target_id=data["target_id"],
        version=data["version"],
        confidence_score=data["confidence_score"],
        trust_weight=data["trust_weight"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _provenance_to_dict(prov: Provenance) -> dict[str, Any]:
    return {
        "collection_id": prov.collection_id,
        "collector_name": prov.collector_name,
        "collected_at": prov.collected_at.isoformat(),
        "source_lineage": prov.source_lineage,
    }
