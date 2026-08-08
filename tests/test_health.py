import pytest
from kubernetes.client import (
    V1ContainerState,
    V1ContainerStateRunning,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1Node,
    V1NodeCondition,
    V1NodeStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodStatus,
)

from multicloud_healer.health import ConsecutiveFailureTracker, node_is_healthy, pod_is_healthy


def _container_status(ready: bool, waiting_reason: str | None = None) -> V1ContainerStatus:
    state = V1ContainerState(
        running=V1ContainerStateRunning() if waiting_reason is None else None,
        waiting=V1ContainerStateWaiting(reason=waiting_reason) if waiting_reason else None,
    )
    return V1ContainerStatus(name="app", image="busybox", image_id="", ready=ready, restart_count=0, state=state)


def _pod(phase: str, container_statuses: list[V1ContainerStatus] | None) -> V1Pod:
    return V1Pod(
        metadata=V1ObjectMeta(name="p1", namespace="default"),
        status=V1PodStatus(phase=phase, container_statuses=container_statuses),
    )


def test_pod_is_healthy_when_running_and_ready():
    pod = _pod("Running", [_container_status(ready=True)])
    assert pod_is_healthy(pod) is True


def test_pod_is_unhealthy_when_not_running():
    pod = _pod("Pending", [_container_status(ready=False)])
    assert pod_is_healthy(pod) is False


def test_pod_is_unhealthy_when_container_not_ready():
    pod = _pod("Running", [_container_status(ready=False)])
    assert pod_is_healthy(pod) is False


def test_pod_is_unhealthy_on_crash_loop_backoff():
    pod = _pod("Running", [_container_status(ready=False, waiting_reason="CrashLoopBackOff")])
    assert pod_is_healthy(pod) is False


def test_pod_is_unhealthy_with_no_container_statuses():
    pod = _pod("Running", None)
    assert pod_is_healthy(pod) is False


def test_pod_is_unhealthy_with_no_status():
    pod = V1Pod(metadata=V1ObjectMeta(name="p1"), status=None)
    assert pod_is_healthy(pod) is False


def _node(ready_status: str | None) -> V1Node:
    conditions = [V1NodeCondition(type="Ready", status=ready_status)] if ready_status else []
    return V1Node(metadata=V1ObjectMeta(name="n1"), status=V1NodeStatus(conditions=conditions))


def test_node_is_healthy_when_ready_true():
    assert node_is_healthy(_node("True")) is True


def test_node_is_unhealthy_when_ready_false():
    assert node_is_healthy(_node("False")) is False


def test_node_is_unhealthy_when_no_ready_condition():
    assert node_is_healthy(_node(None)) is False


def test_consecutive_failure_tracker_fires_exactly_at_threshold():
    tracker = ConsecutiveFailureTracker(threshold=3)
    assert tracker.record("pod-a", healthy=False) is False
    assert tracker.record("pod-a", healthy=False) is False
    assert tracker.record("pod-a", healthy=False) is True


def test_consecutive_failure_tracker_does_not_refire_without_reset():
    tracker = ConsecutiveFailureTracker(threshold=2)
    tracker.record("pod-a", healthy=False)
    assert tracker.record("pod-a", healthy=False) is True
    assert tracker.record("pod-a", healthy=False) is False  # count is now 3, past threshold


def test_consecutive_failure_tracker_resets_on_healthy():
    tracker = ConsecutiveFailureTracker(threshold=2)
    tracker.record("pod-a", healthy=False)
    tracker.record("pod-a", healthy=True)
    assert tracker.count("pod-a") == 0
    assert tracker.record("pod-a", healthy=False) is False


def test_consecutive_failure_tracker_tracks_keys_independently():
    tracker = ConsecutiveFailureTracker(threshold=2)
    tracker.record("pod-a", healthy=False)
    tracker.record("pod-b", healthy=False)
    assert tracker.record("pod-a", healthy=False) is True
    assert tracker.count("pod-b") == 1


def test_consecutive_failure_tracker_rejects_threshold_below_one():
    with pytest.raises(ValueError):
        ConsecutiveFailureTracker(threshold=0)


def test_reset_clears_count():
    tracker = ConsecutiveFailureTracker(threshold=2)
    tracker.record("pod-a", healthy=False)
    tracker.reset("pod-a")
    assert tracker.count("pod-a") == 0
