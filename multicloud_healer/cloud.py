"""Abstracts AWS EKS vs GCP GKE node metadata behind one interface.

EKS and GKE label their nodes differently for the same concepts (node pool,
region, zone), so anything that needs to reason about "which node pool is
this" or "which region" has to know both label sets. This module is that
adapter: detect_provider() looks at which cloud-specific label prefix is
present on a node and returns the matching NodeMetadata, so the rest of the
controller only ever deals with one shape.

Only the EKS labels are exercised against a real cluster in this repo's
demo (kind doesn't run on either cloud), but the GKE path uses real GKE
label names too and is covered by unit tests with fake node objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

REGION_LABEL = "topology.kubernetes.io/region"
ZONE_LABEL = "topology.kubernetes.io/zone"
EKS_NODEGROUP_LABEL = "eks.amazonaws.com/nodegroup"
GKE_NODEPOOL_LABEL = "cloud.google.com/gke-nodepool"


@dataclass(frozen=True)
class NodeMetadata:
    cloud: str  # "aws", "gcp", or "unknown"
    region: str | None
    zone: str | None
    node_pool: str | None


class CloudProvider(Protocol):
    name: str

    def node_metadata(self, labels: dict[str, str]) -> NodeMetadata: ...


class AWSEKSProvider:
    name = "aws"

    def node_metadata(self, labels: dict[str, str]) -> NodeMetadata:
        return NodeMetadata(
            cloud="aws",
            region=labels.get(REGION_LABEL),
            zone=labels.get(ZONE_LABEL),
            node_pool=labels.get(EKS_NODEGROUP_LABEL),
        )


class GCPGKEProvider:
    name = "gcp"

    def node_metadata(self, labels: dict[str, str]) -> NodeMetadata:
        return NodeMetadata(
            cloud="gcp",
            region=labels.get(REGION_LABEL),
            zone=labels.get(ZONE_LABEL),
            node_pool=labels.get(GKE_NODEPOOL_LABEL),
        )


class UnknownCloudProvider:
    name = "unknown"

    def node_metadata(self, labels: dict[str, str]) -> NodeMetadata:
        return NodeMetadata(
            cloud="unknown",
            region=labels.get(REGION_LABEL),
            zone=labels.get(ZONE_LABEL),
            node_pool=None,
        )


def detect_provider(labels: dict[str, str]) -> CloudProvider:
    if EKS_NODEGROUP_LABEL in labels:
        return AWSEKSProvider()
    if GKE_NODEPOOL_LABEL in labels:
        return GCPGKEProvider()
    return UnknownCloudProvider()
