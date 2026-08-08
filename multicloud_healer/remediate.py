"""Remediation actions: restart a pod, cordon + drain a node.

Both take an already-constructed CoreV1Api client so they work the same
against a real cluster or a fake clientset in tests. Drain uses the real
Eviction API (respects PodDisruptionBudgets) rather than a raw delete, and
skips DaemonSet-owned and mirror (static) pods, same as `kubectl drain`.
"""

from __future__ import annotations

import logging

from kubernetes import client
from kubernetes.client import CoreV1Api, V1Eviction, V1ObjectMeta, V1Pod

logger = logging.getLogger("multicloud_healer.remediate")


def restart_pod(api: CoreV1Api, namespace: str, name: str) -> None:
    """Deletes the pod so its owning controller (Deployment/ReplicaSet/etc)
    recreates it fresh. This is the standard "restart a pod" move when a
    container-level restart isn't fixing a stuck pod.
    """
    logger.info("restarting pod %s/%s", namespace, name)
    api.delete_namespaced_pod(name=name, namespace=namespace)


def _is_daemonset_or_mirror_pod(pod: V1Pod) -> bool:
    annotations = (pod.metadata.annotations or {}) if pod.metadata else {}
    if "kubernetes.io/config.mirror" in annotations:
        return True
    owners = (pod.metadata.owner_references or []) if pod.metadata else []
    return any(owner.kind == "DaemonSet" for owner in owners)


def cordon_node(api: CoreV1Api, node_name: str) -> None:
    logger.info("cordoning node %s", node_name)
    api.patch_node(node_name, {"spec": {"unschedulable": True}})


def drain_node(api: CoreV1Api, node_name: str, grace_period_seconds: int = 30) -> list[str]:
    """Evicts every non-DaemonSet, non-mirror pod on node_name. Returns the
    names of pods an eviction was attempted for.
    """
    pods = api.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    evicted: list[str] = []

    for pod in pods:
        if _is_daemonset_or_mirror_pod(pod):
            continue

        eviction = V1Eviction(
            metadata=V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace),
            delete_options=client.V1DeleteOptions(grace_period_seconds=grace_period_seconds),
        )
        logger.info("evicting pod %s/%s from node %s", pod.metadata.namespace, pod.metadata.name, node_name)
        api.create_namespaced_pod_eviction(
            name=pod.metadata.name, namespace=pod.metadata.namespace, body=eviction
        )
        evicted.append(pod.metadata.name)

    return evicted


def cordon_and_drain_node(api: CoreV1Api, node_name: str, grace_period_seconds: int = 30) -> list[str]:
    cordon_node(api, node_name)
    return drain_node(api, node_name, grace_period_seconds=grace_period_seconds)
