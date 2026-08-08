"""Self-healing control loop: poll pod/node health, remediate after repeated
failures, log every action taken.

Deliberately reacts only after --failure-threshold consecutive bad checks
for the same pod or node, not on the first bad check, so a brief network
blip or a slow readiness probe doesn't trigger a restart or a drain.
"""

from __future__ import annotations

import argparse
import logging
import time

from kubernetes import client
from kubernetes import config as kube_config
from kubernetes.client import CoreV1Api

from multicloud_healer.cloud import detect_provider
from multicloud_healer.health import ConsecutiveFailureTracker, node_is_healthy, pod_is_healthy
from multicloud_healer.remediate import cordon_and_drain_node, restart_pod

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("multicloud_healer.controller")


class SelfHealingController:
    def __init__(
        self,
        api: CoreV1Api,
        namespace: str,
        label_selector: str,
        failure_threshold: int,
        watch_nodes: bool = False,
    ) -> None:
        self.api = api
        self.namespace = namespace
        self.label_selector = label_selector
        self.watch_nodes = watch_nodes
        self.pod_tracker = ConsecutiveFailureTracker(failure_threshold)
        self.node_tracker = ConsecutiveFailureTracker(failure_threshold)

    def poll_pods(self) -> list[str]:
        pods = self.api.list_namespaced_pod(self.namespace, label_selector=self.label_selector).items
        remediated = []
        for pod in pods:
            key = f"{pod.metadata.namespace}/{pod.metadata.name}"
            healthy = pod_is_healthy(pod)
            if self.pod_tracker.record(key, healthy):
                logger.warning(
                    "pod %s unhealthy for %d consecutive checks, restarting",
                    key,
                    self.pod_tracker.threshold,
                )
                restart_pod(self.api, pod.metadata.namespace, pod.metadata.name)
                self.pod_tracker.reset(key)
                remediated.append(key)
        return remediated

    def poll_nodes(self) -> list[str]:
        if not self.watch_nodes:
            return []
        nodes = self.api.list_node().items
        remediated = []
        for node in nodes:
            name = node.metadata.name
            healthy = node_is_healthy(node)
            if self.node_tracker.record(name, healthy):
                labels = node.metadata.labels or {}
                provider = detect_provider(labels)
                meta = provider.node_metadata(labels)
                logger.warning(
                    "node %s (%s) unhealthy for %d consecutive checks, cordoning and draining",
                    name,
                    meta.cloud,
                    self.node_tracker.threshold,
                )
                cordon_and_drain_node(self.api, name)
                self.node_tracker.reset(name)
                remediated.append(name)
        return remediated

    def run(self, poll_interval_seconds: float, cycles: int = 0) -> None:
        """cycles=0 means run forever."""
        cycle = 0
        while cycles == 0 or cycle < cycles:
            cycle += 1
            pod_actions = self.poll_pods()
            node_actions = self.poll_nodes()
            logger.info(
                "cycle %d: pod_actions=%s node_actions=%s", cycle, pod_actions, node_actions
            )
            if cycles == 0 or cycle < cycles:
                time.sleep(poll_interval_seconds)


def build_api(context: str | None) -> CoreV1Api:
    """Loads in-cluster config when running as a pod (has a service account
    token mounted), otherwise falls back to the local kubeconfig used for
    the kind demo.
    """
    try:
        kube_config.load_incluster_config()
    except kube_config.ConfigException:
        kube_config.load_kube_config(context=context)
    return client.CoreV1Api()


def main() -> None:
    parser = argparse.ArgumentParser(description="multicloud-healer self-healing controller")
    parser.add_argument("--context", default=None, help="kubeconfig context, default is current context")
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--label-selector", default="")
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--cycles", type=int, default=0, help="0 means run forever")
    parser.add_argument("--watch-nodes", action="store_true")
    args = parser.parse_args()

    api = build_api(args.context)
    controller = SelfHealingController(
        api=api,
        namespace=args.namespace,
        label_selector=args.label_selector,
        failure_threshold=args.failure_threshold,
        watch_nodes=args.watch_nodes,
    )
    logger.info(
        "starting controller: namespace=%s selector=%r threshold=%d watch_nodes=%s",
        args.namespace,
        args.label_selector,
        args.failure_threshold,
        args.watch_nodes,
    )
    controller.run(args.poll_interval, cycles=args.cycles)


if __name__ == "__main__":
    main()
