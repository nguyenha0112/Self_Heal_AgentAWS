# W11 AI Contract Sync Evidence - CDO-02

This folder is the handoff package for AI Team integration.

## What is confirmed

- AI latest checked commit: `f0248ce667fa77cd5cbe1abc0d39ef6e81b321c9`.
- EKS cluster exists and is ACTIVE:
  - `cdo-eks-cluster-dev`
  - Kubernetes `1.30`
  - region `us-east-1`
  - account `938145531618`
- CDO kubeconfig was updated for the EKS cluster.
- CDO action boundary is aligned: AI decides, CDO validates/executes/verifies/audits.
- `DELETE_POD` is not allowed by current CDO alignment.
- SQS is treated as optional CDO-internal telemetry buffer unless AI publishes a queue ARN/interface.

## What AI needs to provide

1. Hosted mock API base URL for:
   - `POST /v1/detect`
   - `POST /v1/decide`
   - `POST /v1/verify`
2. Auth details and sample headers for the mock API.
3. Confirmation that CDO-02 should use tenant UUID `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`.
4. The allowed `suspected_fault_type` values.
5. Whether `pattern_type=deferred` must always use GitOps/PR instead of direct Kubernetes mutation.
6. Whether AI mock responses can cover `PATCH_MEMORY_LIMIT`, `SCALE_REPLICAS`, `ROLLOUT_UNDO`, and `ROTATE_SECRET`.
7. Whether topology mapping must be registered before tests:
   - service: `checkout-svc`
   - namespace: `tenant-a`
   - deployment: `cdo-sample-api`

## Evidence files

- `ai-latest-commit.txt`: latest AI commit and contract alignment.
- `cdo-eks-output.txt`: AWS/EKS evidence from CDO workstation.
- `detect-request.json`: CDO request shape for `/v1/detect`.
- `decide-response.json`: AI mock response shape for `/v1/decide`.
- `verify-request.json`: CDO request shape for `/v1/verify`.
- `safety-gate-result.txt`: pass/deny decisions CDO will enforce.
- `kubectl-before-after.txt`: commands for capturing live Kubernetes restart evidence.
- `topology-graph-sample.json`: topology graph and CDO service-to-namespace-to-deployment mapping for AI.
- `manifests/workloads/tenant-a-sample-app.yaml`: public `podinfo` app deployment used as the real sandbox workload.

## Live demo path

When Kubernetes API access is available from the workstation or CI runner:

```powershell
kubectl apply -f manifests/namespaces/platform.yaml
kubectl apply -f manifests/namespaces/tenant-a.yaml
kubectl apply -f manifests/namespaces/tenant-b.yaml
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml
kubectl get deploy,pod,svc -n tenant-a -o wide
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 9797:9797
curl http://127.0.0.1:9898/healthz
curl http://127.0.0.1:9898/readyz
curl http://127.0.0.1:9898/metrics
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=120s
kubectl get deploy,pod,svc -n tenant-a -o wide
```

## Current limitation

`kubectl` requests timed out from this workstation after kubeconfig was updated. EKS config confirms the API endpoint is private-only:

- `endpointPublicAccess=false`
- `endpointPrivateAccess=true`

The AWS control-plane evidence is real and confirmed, while live Kubernetes before/after pod evidence must be captured from inside the VPC path, such as VPN, bastion, CloudShell/VPC-attached runner, or CI runner with private subnet reachability.
