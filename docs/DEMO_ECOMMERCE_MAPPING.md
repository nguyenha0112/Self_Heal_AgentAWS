# Demo Ecommerce Workload Mapping

This maps the real ecommerce demo app from `D:\Xbrain\Phase2\react-ecommerce`
into the CDO self-heal EKS demo.

## Source App

- Git repo: `https://github.com/hailv1209/Capstone_phase2_Demo_Ecommerce.git`
- Local path: `D:\Xbrain\Phase2\react-ecommerce`
- CDO workload namespaces: `tenant-a`, `tenant-b`
- Services exposed to AI/CDO: `ecommerce-api`, `ecommerce-web`

The API app exposes `/metrics` with `http_requests_total`,
`http_request_duration_seconds_bucket`, and fault injection endpoints:

- `POST /debug/fault/error-rate`
- `POST /debug/fault/latency`
- `POST /debug/fault/memory`
- `POST /debug/fault/reset`

## Build And Push Images

Run from the ecommerce app repo. Docker must be running before this step.

```powershell
cd D:\Xbrain\Phase2\react-ecommerce
docker info

$env:AWS_REGION = "ap-southeast-1"
$env:AWS_ACCOUNT_ID = "<aws-account-id>"
$env:IMAGE_TAG = "<git-sha-or-demo-tag>"
& "D:\Program Files\Git\bin\bash.exe" scripts/ecr-build-push.sh
```

Expected ECR images:

```text
<aws-account-id>.dkr.ecr.<region>.amazonaws.com/tf3-cdo02/ecommerce-api:<tag>
<aws-account-id>.dkr.ecr.<region>.amazonaws.com/tf3-cdo02/ecommerce-web:<tag>
```

## Render Manifests Into CDO

Run from this CDO repo:

```powershell
cd D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS

powershell -ExecutionPolicy Bypass -File .\scripts\render-ecommerce-demo-manifests.ps1 `
  -ApiImage "<aws-account-id>.dkr.ecr.<region>.amazonaws.com/tf3-cdo02/ecommerce-api:<tag>" `
  -WebImage "<aws-account-id>.dkr.ecr.<region>.amazonaws.com/tf3-cdo02/ecommerce-web:<tag>"
```

The script renders these files under `manifests/workloads/`:

- `ecommerce-api-tenant-a.yaml`
- `ecommerce-api-tenant-b.yaml`
- `ecommerce-web-tenant-a.yaml`
- `ecommerce-web-tenant-b.yaml`

The `cdo-ecommerce-demo` ServiceMonitor scrapes only `service=ecommerce-api`.
The web workload is still deployed for the demo frontend and dependency graph,
but it does not expose Prometheus metrics.

## Required Database Secret

The API readiness probe checks database connectivity, so apply a real
`ecommerce-db` Secret before rolling out `ecommerce-api`.

Use the examples from:

```text
D:\Xbrain\Phase2\react-ecommerce\manifests\secrets\ecommerce-db-tenant-a.example.yaml
D:\Xbrain\Phase2\react-ecommerce\manifests\secrets\ecommerce-db-tenant-b.example.yaml
```

Update `DATABASE_URL` for each tenant, then apply:

```powershell
kubectl apply -f <tenant-a-db-secret.yaml>
kubectl apply -f <tenant-b-db-secret.yaml>
```

Run the app migrations and seed jobs from the ecommerce repo if the database is
new. Do this before expecting `/ready` to pass.

## Deploy To EKS

```powershell
kubectl apply -f manifests/workloads/ecommerce-api-tenant-a.yaml
kubectl apply -f manifests/workloads/ecommerce-api-tenant-b.yaml
kubectl apply -f manifests/workloads/ecommerce-web-tenant-a.yaml
kubectl apply -f manifests/workloads/ecommerce-web-tenant-b.yaml
kubectl apply -f manifests/observability/servicemonitor-ecommerce-demo.yaml

kubectl rollout status deployment/ecommerce-api -n tenant-a --timeout=180s
kubectl rollout status deployment/ecommerce-web -n tenant-a --timeout=180s
kubectl rollout status deployment/ecommerce-api -n tenant-b --timeout=180s
kubectl rollout status deployment/ecommerce-web -n tenant-b --timeout=180s
```

## Validate Telemetry

```powershell
kubectl port-forward -n tenant-a svc/ecommerce-api 3000:3000
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/ready
curl http://127.0.0.1:3000/metrics
```

Trigger an error-rate fault:

```powershell
curl -X POST http://127.0.0.1:3000/debug/fault/error-rate `
  -H "Content-Type: application/json" `
  -d "{\"error_rate\":0.5}"
```

PromQL check after Prometheus scrapes the ServiceMonitor:

```promql
(
  (sum(rate(http_requests_total{deployment="ecommerce-api",code=~"5.."}[1m])) or vector(0))
  +
  (sum(rate(http_requests_total{deployment="ecommerce-api",status=~"5.."}[1m])) or vector(0))
)
/
sum(rate(http_requests_total{deployment="ecommerce-api"}[1m]))
```

## CDO/AI Contract Mapping

- Kubernetes labels include `tier=cdo-ecommerce-demo` for ServiceMonitor
  selection.
- Kubernetes labels include `selfheal.ai/service=ecommerce-api` or
  `selfheal.ai/service=ecommerce-web` for AI/CDO service identity.
- App telemetry labels use `system=E-COMMERCE`.
- AI platform profile includes `ecommerce-api` and `ecommerce-web`.
- CDO Prometheus queries accept both `code=~"5.."` and `status=~"5.."` because
  podinfo uses `code`, while the ecommerce app uses `status`.
