from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import stix2
from stix2.v21 import Bundle, DomainName, Indicator, IPv4Address, IPv6Address, Vulnerability

from intelgraph.core.entity import BaseEntity
from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node


def _stix_id(prefix: str, seed: str) -> str:
    ns = uuid.NAMESPACE_DNS
    return f"{prefix}--{uuid.uuid5(ns, seed)}"


def _to_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return (
        dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if dt.tzinfo
        else dt.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )


def _labels(entity: BaseEntity) -> list[str]:
    labels = [entity.entity_type.type_name]
    if entity.confidence_score >= 70:
        labels.append("high-confidence")
    elif entity.confidence_score >= 40:
        labels.append("medium-confidence")
    else:
        labels.append("low-confidence")
    return labels


def _external_refs(entity: BaseEntity) -> list[dict[str, str]]:
    refs = []
    for ev in getattr(entity, "evidence", ()):
        if ev.source and ev.content:
            refs.append(
                {
                    "source_name": ev.source,
                    "description": ev.content[:200],
                }
            )
    return refs


def entity_to_stix(node: Node) -> list[dict[str, Any]]:
    entity = node.entity
    etype = entity.entity_type.type_name
    stix_objects: list[dict[str, Any]] = []

    created = _to_timestamp(entity.created_at)
    modified = _to_timestamp(entity.updated_at)
    confidence = entity.confidence_score
    labels = _labels(entity)

    if isinstance(entity, IPAddress):
        ip = entity.ip
        if ":" in ip:
            obj = IPv6Address(
                id=_stix_id("ipv6-addr", ip),
                value=ip,
                allow_custom=True,
                custom_properties={
                    "x_intelgraph_id": entity.id,
                    "x_intelgraph_entity_type": etype,
                    "x_confidence": confidence,
                    "x_labels": labels,
                    "x_created": created,
                    "x_modified": modified,
                },
            )
        else:
            obj = IPv4Address(
                id=_stix_id("ipv4-addr", ip),
                value=ip,
                allow_custom=True,
                custom_properties={
                    "x_intelgraph_id": entity.id,
                    "x_intelgraph_entity_type": etype,
                    "x_confidence": confidence,
                    "x_labels": labels,
                    "x_created": created,
                    "x_modified": modified,
                },
            )
        stix_objects.append(obj)

        indicator = Indicator(
            id=_stix_id("indicator", f"indicator-{ip}"),
            name=f"Malicious IP: {ip}",
            description=f"IP address {ip} identified as threat by IntelGraph",
            pattern=f"[ipv4-addr:value = '{ip}']",
            pattern_type="stix",
            created=created,
            modified=modified,
            confidence=confidence,
            labels=labels + ["indicator"],
            valid_from=created,
            allow_custom=True,
            custom_properties={
                "x_intelgraph_entity_id": entity.id,
            },
        )
        stix_objects.append(indicator)

    elif isinstance(entity, Domain):
        domain = entity.domain_name
        obj = DomainName(
            id=_stix_id("domain-name", domain),
            value=domain,
            allow_custom=True,
            custom_properties={
                "x_intelgraph_id": entity.id,
                "x_intelgraph_entity_type": etype,
                "x_confidence": confidence,
                "x_labels": labels,
                "x_created": created,
                "x_modified": modified,
            },
        )
        stix_objects.append(obj)

        indicator = Indicator(
            id=_stix_id("indicator", f"indicator-{domain}"),
            name=f"Malicious Domain: {domain}",
            description=f"Domain {domain} identified as threat by IntelGraph",
            pattern=f"[domain-name:value = '{domain}']",
            pattern_type="stix",
            created=created,
            modified=modified,
            confidence=confidence,
            labels=labels + ["indicator"],
            valid_from=created,
            allow_custom=True,
            custom_properties={
                "x_intelgraph_entity_id": entity.id,
            },
        )
        stix_objects.append(indicator)

    elif isinstance(entity, CveEntity):
        cve_id = entity.cve_id.upper()
        desc = entity.short_description or entity.vulnerability_name or f"CVE: {cve_id}"
        obj = Vulnerability(
            id=_stix_id("vulnerability", cve_id),
            name=cve_id,
            description=desc,
            created=created,
            modified=modified,
            confidence=confidence,
            labels=labels,
            external_references=_external_refs(entity),
            allow_custom=True,
            custom_properties={
                "x_intelgraph_id": entity.id,
                "x_intelgraph_entity_type": etype,
                "x_known_ransomware_use": entity.known_ransomware_use,
                "x_vendor_project": entity.vendor_project,
                "x_product": entity.product,
            },
        )
        stix_objects.append(obj)

        indicator = Indicator(
            id=_stix_id("indicator", f"indicator-{cve_id}"),
            name=f"CVE: {cve_id}",
            description=desc,
            pattern=f"[vulnerability:name = '{cve_id}']",
            pattern_type="stix",
            created=created,
            modified=modified,
            confidence=confidence,
            labels=labels + ["indicator"],
            valid_from=created,
            allow_custom=True,
            custom_properties={
                "x_intelgraph_entity_id": entity.id,
            },
        )
        stix_objects.append(indicator)

    return stix_objects


def edge_to_stix(edge: Edge, graph: IntelligenceGraph) -> dict[str, Any] | None:
    rel = edge.relationship
    source_node = graph.nodes.get(edge.source_id)
    target_node = graph.nodes.get(edge.target_id)
    if not source_node or not target_node:
        return None

    source_stix_ids = entity_to_stix(source_node)
    target_stix_ids = entity_to_stix(target_node)
    if not source_stix_ids or not target_stix_ids:
        return None

    source_ref = source_stix_ids[0]["id"]
    target_ref = target_stix_ids[0]["id"]

    rel_type = rel.type.name.lower()
    stix_rel_map = {
        "related_to": "related-to",
        "connected_to": "connected-to",
        "hosted_on": "hosted-on",
        "resolves_to": "resolves-to",
        "subdomain_of": "subdomain-of",
        "uses": "uses",
        "owns": "owns",
        "associated_with": "associated-with",
        "registered_to": "registered-to",
    }
    stix_relationship_type = stix_rel_map.get(rel_type, "related-to")

    obj = stix2.Relationship(
        id=_stix_id("relationship", f"{edge.source_id}-{edge.target_id}-{rel_type}"),
        relationship_type=stix_relationship_type,
        source_ref=source_ref,
        target_ref=target_ref,
        created=_to_timestamp(rel.created_at),
        modified=_to_timestamp(rel.last_seen),
        confidence=rel.confidence_score,
        allow_custom=True,
        custom_properties={
            "x_intelgraph_edge_id": edge.id,
            "x_occurrence_count": rel.occurrence_count,
        },
    )
    return obj


def graph_to_bundle(
    graph: IntelligenceGraph,
    since: datetime | None = None,
    filter_type: str | None = None,
) -> Bundle:
    stix_objects: list[dict[str, Any]] = []

    stix_label_map = {
        "ipv4-addr": ["ipv4-addr", "indicator"],
        "ipv6-addr": ["ipv6-addr", "indicator"],
        "domain-name": ["domain-name", "indicator"],
        "vulnerability": ["vulnerability", "indicator"],
    }
    stix_types_for = stix_label_map.get(filter_type) if filter_type else None

    node_stix_ids: dict[str, list[str]] = {}
    for node_id, node in graph.nodes.items():
        if since is not None:
            fs = node.entity.first_seen
            if fs and fs < since:
                continue
        objs = entity_to_stix(node)
        allowed = stix_types_for
        if allowed:
            objs = [o for o in objs if o.get("type") in allowed]
        for obj in objs:
            stix_objects.append(obj)
        node_stix_ids[node_id] = [o["id"] for o in objs]

    for _edge_id, edge in graph.edges.items():
        if edge.source_id in node_stix_ids and edge.target_id in node_stix_ids:
            if filter_type and filter_type != "relationship":
                continue
            rel_obj = edge_to_stix(edge, graph)
            if rel_obj:
                stix_objects.append(rel_obj)

    type_str = None
    if filter_type:
        type_str = filter_type.replace("-", "_")

    bundle = Bundle(
        id=_stix_id("bundle", f"intelgraph-export{'-' + type_str if type_str else ''}"),
        objects=stix_objects,
        allow_custom=True,
    )
    return bundle


def graph_to_bundle_json(
    graph: IntelligenceGraph,
    since: datetime | None = None,
    filter_type: str | None = None,
) -> str:
    bundle = graph_to_bundle(graph, since=since, filter_type=filter_type)
    return bundle.serialize(pretty=True)
