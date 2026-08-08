#!/bin/bash
set -e
cd "$(dirname "$0")/.."

CONTEXT=kind-healer-demo
PY=.venv/bin/python
export PYTHONPATH=.

kubectl --context "$CONTEXT" delete -f demo/flaky-app.yaml --wait=true >/dev/null 2>&1 || true
kubectl --context "$CONTEXT" wait --for=delete pod -l app=flaky-app --timeout=30s >/dev/null 2>&1 || true

echo '$ kubectl apply -f demo/flaky-app.yaml'
kubectl --context "$CONTEXT" apply -f demo/flaky-app.yaml

echo
echo "# the readiness probe on this pod always fails, it stays 0/1 forever without help"
sleep 6
echo '$ kubectl get pods -l app=flaky-app'
kubectl --context "$CONTEXT" get pods -l app=flaky-app

echo
echo '$ python -m multicloud_healer.controller --context kind-healer-demo --label-selector app=flaky-app --failure-threshold 3 --poll-interval 2 --cycles 6'
$PY -m multicloud_healer.controller \
  --context "$CONTEXT" \
  --namespace default \
  --label-selector app=flaky-app \
  --failure-threshold 3 \
  --poll-interval 2 \
  --cycles 6

echo
echo '$ kubectl get pods -l app=flaky-app'
kubectl --context "$CONTEXT" get pods -l app=flaky-app

kubectl --context "$CONTEXT" delete -f demo/flaky-app.yaml >/dev/null 2>&1
echo
echo "demo app cleaned up."
