from multicloud_healer.cloud import (
    AWSEKSProvider,
    GCPGKEProvider,
    UnknownCloudProvider,
    detect_provider,
)


def test_detect_provider_eks():
    labels = {
        "eks.amazonaws.com/nodegroup": "gpu-pool-a",
        "topology.kubernetes.io/region": "us-west-2",
        "topology.kubernetes.io/zone": "us-west-2a",
    }
    provider = detect_provider(labels)
    assert isinstance(provider, AWSEKSProvider)

    meta = provider.node_metadata(labels)
    assert meta.cloud == "aws"
    assert meta.region == "us-west-2"
    assert meta.zone == "us-west-2a"
    assert meta.node_pool == "gpu-pool-a"


def test_detect_provider_gke():
    labels = {
        "cloud.google.com/gke-nodepool": "ray-workers",
        "topology.kubernetes.io/region": "us-central1",
        "topology.kubernetes.io/zone": "us-central1-a",
    }
    provider = detect_provider(labels)
    assert isinstance(provider, GCPGKEProvider)

    meta = provider.node_metadata(labels)
    assert meta.cloud == "gcp"
    assert meta.region == "us-central1"
    assert meta.node_pool == "ray-workers"


def test_detect_provider_unknown_for_local_cluster():
    labels = {"kubernetes.io/hostname": "kind-control-plane"}
    provider = detect_provider(labels)
    assert isinstance(provider, UnknownCloudProvider)

    meta = provider.node_metadata(labels)
    assert meta.cloud == "unknown"
    assert meta.node_pool is None


def test_eks_labels_take_precedence_if_both_present_somehow():
    labels = {
        "eks.amazonaws.com/nodegroup": "pool-a",
        "cloud.google.com/gke-nodepool": "pool-b",
    }
    provider = detect_provider(labels)
    assert isinstance(provider, AWSEKSProvider)


def test_node_metadata_missing_labels_returns_none_fields():
    provider = AWSEKSProvider()
    meta = provider.node_metadata({})
    assert meta.region is None
    assert meta.zone is None
    assert meta.node_pool is None
