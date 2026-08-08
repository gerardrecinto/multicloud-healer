from unittest.mock import MagicMock

from kubernetes.client import (
    V1ContainerState,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1Node,
    V1NodeCondition,
    V1NodeStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodStatus,
)

from multicloud_healer.controller import SelfHealingController


def _unhealthy_pod(name: str) -> V1Pod:
    status = V1ContainerStatus(
        name="app",
        image="busybox",
        image_id="",
        ready=False,
        restart_count=5,
        state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="CrashLoopBackOff")),
    )
    return V1Pod(
        metadata=V1ObjectMeta(name=name, namespace="default"),
        status=V1PodStatus(phase="Running", container_statuses=[status]),
    )


def _healthy_pod(name: str) -> V1Pod:
    status = V1ContainerStatus(name="app", image="busybox", image_id="", ready=True, restart_count=0, state=None)
    return V1Pod(
        metadata=V1ObjectMeta(name=name, namespace="default"),
        status=V1PodStatus(phase="Running", container_statuses=[status]),
    )


def test_poll_pods_restarts_after_threshold_consecutive_failures():
    api = MagicMock()
    api.list_namespaced_pod.return_value.items = [_unhealthy_pod("flaky-app-1")]

    controller = SelfHealingController(
        api=api, namespace="default", label_selector="app=flaky-app", failure_threshold=3
    )

    assert controller.poll_pods() == []
    assert controller.poll_pods() == []
    assert controller.poll_pods() == ["default/flaky-app-1"]
    api.delete_namespaced_pod.assert_called_once_with(name="flaky-app-1", namespace="default")


def test_poll_pods_does_not_restart_healthy_pods():
    api = MagicMock()
    api.list_namespaced_pod.return_value.items = [_healthy_pod("app-1")]

    controller = SelfHealingController(
        api=api, namespace="default", label_selector="app=app", failure_threshold=3
    )

    for _ in range(5):
        assert controller.poll_pods() == []
    api.delete_namespaced_pod.assert_not_called()


def test_poll_pods_resets_after_remediation_so_it_can_fire_again():
    api = MagicMock()
    api.list_namespaced_pod.return_value.items = [_unhealthy_pod("flaky-app-1")]

    controller = SelfHealingController(
        api=api, namespace="default", label_selector="app=flaky-app", failure_threshold=2
    )

    controller.poll_pods()
    first_remediation = controller.poll_pods()
    assert first_remediation == ["default/flaky-app-1"]

    controller.poll_pods()
    second_remediation = controller.poll_pods()
    assert second_remediation == ["default/flaky-app-1"]
    assert api.delete_namespaced_pod.call_count == 2


def test_poll_nodes_disabled_by_default():
    api = MagicMock()
    controller = SelfHealingController(
        api=api, namespace="default", label_selector="", failure_threshold=1
    )
    assert controller.poll_nodes() == []
    api.list_node.assert_not_called()


def test_poll_nodes_cordons_and_drains_after_threshold():
    api = MagicMock()
    unhealthy_node = V1Node(
        metadata=V1ObjectMeta(name="node-1", labels={"eks.amazonaws.com/nodegroup": "pool-a"}),
        status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="False")]),
    )
    api.list_node.return_value.items = [unhealthy_node]
    api.list_pod_for_all_namespaces.return_value.items = []

    controller = SelfHealingController(
        api=api, namespace="default", label_selector="", failure_threshold=1, watch_nodes=True
    )

    remediated = controller.poll_nodes()

    assert remediated == ["node-1"]
    api.patch_node.assert_called_once_with("node-1", {"spec": {"unschedulable": True}})
