"""Health evaluation for pods and nodes, plus consecutive-failure tracking.

pod_is_healthy / node_is_healthy take the actual kubernetes client model
objects (V1Pod, V1Node) so the logic matches what the real API returns.
ConsecutiveFailureTracker is deliberately k8s-agnostic (keyed by plain
strings) so a self-healing controller doesn't act on a single bad health
check, only after --failure-threshold consecutive bad checks for the same
object.
"""

from __future__ import annotations

from kubernetes.client import V1Node, V1Pod


def pod_is_healthy(pod: V1Pod) -> bool:
    status = pod.status
    if status is None or status.phase != "Running":
        return False

    container_statuses = status.container_statuses or []
    if not container_statuses:
        return False

    for cs in container_statuses:
        if not cs.ready:
            return False
        waiting = cs.state.waiting if cs.state else None
        if waiting is not None and waiting.reason == "CrashLoopBackOff":
            return False

    return True


def node_is_healthy(node: V1Node) -> bool:
    status = node.status
    if status is None or not status.conditions:
        return False

    for condition in status.conditions:
        if condition.type == "Ready":
            return condition.status == "True"

    return False


class ConsecutiveFailureTracker:
    """Tracks consecutive unhealthy checks per key. record() returns True the
    moment a key's consecutive failure count reaches the threshold, so the
    caller remediates once per incident, not once per poll cycle.
    """

    def __init__(self, threshold: int) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.threshold = threshold
        self._counts: dict[str, int] = {}

    def record(self, key: str, healthy: bool) -> bool:
        if healthy:
            self._counts[key] = 0
            return False
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] == self.threshold

    def reset(self, key: str) -> None:
        self._counts.pop(key, None)

    def count(self, key: str) -> int:
        return self._counts.get(key, 0)
