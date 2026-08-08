from unittest.mock import MagicMock

from kubernetes.client import V1ObjectMeta, V1OwnerReference, V1Pod

from multicloud_healer.remediate import cordon_and_drain_node, cordon_node, drain_node, restart_pod


def test_restart_pod_deletes_the_pod():
    api = MagicMock()
    restart_pod(api, namespace="default", name="app-abc123")
    api.delete_namespaced_pod.assert_called_once_with(name="app-abc123", namespace="default")


def test_cordon_node_patches_unschedulable():
    api = MagicMock()
    cordon_node(api, "node-1")
    api.patch_node.assert_called_once_with("node-1", {"spec": {"unschedulable": True}})


def _pod(name: str, namespace: str = "default", owner_kind: str | None = None, mirror: bool = False) -> V1Pod:
    owners = [V1OwnerReference(api_version="apps/v1", kind=owner_kind, name="x", uid="u1")] if owner_kind else None
    annotations = {"kubernetes.io/config.mirror": "true"} if mirror else None
    return V1Pod(
        metadata=V1ObjectMeta(name=name, namespace=namespace, owner_references=owners, annotations=annotations)
    )


def test_drain_node_evicts_regular_pods():
    api = MagicMock()
    api.list_pod_for_all_namespaces.return_value.items = [
        _pod("app-1", owner_kind="ReplicaSet"),
        _pod("app-2", owner_kind="ReplicaSet"),
    ]

    evicted = drain_node(api, "node-1")

    assert evicted == ["app-1", "app-2"]
    assert api.create_namespaced_pod_eviction.call_count == 2


def test_drain_node_skips_daemonset_pods():
    api = MagicMock()
    api.list_pod_for_all_namespaces.return_value.items = [
        _pod("app-1", owner_kind="ReplicaSet"),
        _pod("kube-proxy-xyz", owner_kind="DaemonSet"),
    ]

    evicted = drain_node(api, "node-1")

    assert evicted == ["app-1"]
    assert api.create_namespaced_pod_eviction.call_count == 1


def test_drain_node_skips_mirror_pods():
    api = MagicMock()
    api.list_pod_for_all_namespaces.return_value.items = [
        _pod("app-1", owner_kind="ReplicaSet"),
        _pod("etcd-control-plane", mirror=True),
    ]

    evicted = drain_node(api, "node-1")

    assert evicted == ["app-1"]


def test_drain_node_filters_by_field_selector():
    api = MagicMock()
    api.list_pod_for_all_namespaces.return_value.items = []

    drain_node(api, "node-1")

    api.list_pod_for_all_namespaces.assert_called_once_with(field_selector="spec.nodeName=node-1")


def test_cordon_and_drain_node_does_both_in_order():
    api = MagicMock()
    api.list_pod_for_all_namespaces.return_value.items = [_pod("app-1", owner_kind="ReplicaSet")]

    evicted = cordon_and_drain_node(api, "node-1")

    api.patch_node.assert_called_once_with("node-1", {"spec": {"unschedulable": True}})
    assert evicted == ["app-1"]
