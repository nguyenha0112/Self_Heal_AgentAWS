# CDO-02 Sample Workload

CDO-02 uses `stefanprodan/podinfo` as the public demo application for the W11/W12 self-heal flow.

Why this app is used instead of a trivial echo container:

- It is a real public Kubernetes demo app.
- It exposes liveness and readiness endpoints: `/healthz`, `/readyz`.
- It exposes Prometheus metrics on port `9797`.
- It supports HTTP behavior useful for telemetry and self-heal demos.
- It is lightweight enough for the EKS sandbox.

Primary CDO topology mapping:

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

Useful commands once the EKS private endpoint is reachable:

```powershell
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=120s
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 9797:9797
curl http://127.0.0.1:9898/healthz
curl http://127.0.0.1:9898/readyz
curl http://127.0.0.1:9898/metrics
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
```

Public source:

```text
https://github.com/stefanprodan/podinfo
```
