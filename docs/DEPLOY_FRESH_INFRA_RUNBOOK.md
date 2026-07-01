# Fresh Infra Deploy Runbook

Runbook nay mo ta cac buoc deploy moi ha tang CDO tren AWS/EKS, cap nhat cho
demo ecommerce app thay vi chi dung workload rong/podinfo. Tai lieu chi la
huong dan thao tac; khong co buoc nao trong file nay da duoc tu dong chay.

## Thong Tin Deploy

- AWS account hien tai: `593777010472`
- Region: `ap-southeast-1`
- Terraform state bucket: `cdo-tf-state-593777010472-ap-southeast-1-dev`
- Terraform state key: `envs/dev/terraform.tfstate`
- EKS cluster: `cdo-eks-cluster-dev`
- Executor ECR repo: `593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/cdo-executor`
- Audit bucket mau: `cdo-audit-593777010472-cdo-eks-cluster-dev-dev`
- CDO repo local: `D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS`
- Ecommerce demo repo local: `D:\Xbrain\Phase2\react-ecommerce`
- Ecommerce demo GitHub: `https://github.com/hailv1209/Capstone_phase2_Demo_Ecommerce.git`
- AI Engine local: `D:\Xbrain\Phase2\Capstone-Phase-2-Code\tf-3\ai\ai-engine\detect_decide_verify`

## 1. Preflight

Chay tu root CDO repo:

```powershell
cd D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS

aws sts get-caller-identity
aws configure get region
terraform version
kubectl version --client=true
helm version
docker --version
docker info
```

Yeu cau:

- AWS CLI tro dung account deploy.
- Region la `ap-southeast-1`.
- Terraform `>= 1.10`.
- Docker Desktop/daemon dang chay truoc khi build executor, AI Engine, va demo app images.
- Git Bash ton tai tai `D:\Program Files\Git\bin\bash.exe` neu dung script build cua ecommerce repo.

## 2. Cap Nhat Terraform Account/Backend

Neu deploy fresh tren account `593777010472`, kiem tra `infra/envs/dev/providers.tf`:

```hcl
backend "s3" {
  bucket       = "cdo-tf-state-593777010472-ap-southeast-1-dev"
  key          = "envs/dev/terraform.tfstate"
  region       = "ap-southeast-1"
  use_lockfile = true
  encrypt      = true
}
```

Kiem tra `infra/envs/dev/variables.tf`:

```hcl
variable "aws_account_id" { default = "593777010472" }
```

## 3. Bootstrap S3 Remote State

Chi can lam mot lan cho account/region moi:

```powershell
terraform -chdir=infra\bootstrap init
terraform -chdir=infra\bootstrap apply -auto-approve
```

Verify bucket:

```powershell
aws s3api head-bucket `
  --bucket cdo-tf-state-593777010472-ap-southeast-1-dev `
  --region ap-southeast-1
```

## 4. Init, Plan, Apply Terraform Env Dev

Them Helm repo cache truoc:

```powershell
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
```

Chay Terraform:

```powershell
terraform -chdir=infra\envs\dev init -reconfigure
terraform -chdir=infra\envs\dev validate
terraform -chdir=infra\envs\dev plan "-out=tfplan-dev.out"
terraform -chdir=infra\envs\dev apply tfplan-dev.out
```

Verify:

```powershell
terraform -chdir=infra\envs\dev plan -detailed-exitcode
terraform -chdir=infra\envs\dev output
```

Ket qua mong doi: plan exit code `0`, khong co changes.

## 5. Update Kubeconfig Va Verify EKS

```powershell
aws eks update-kubeconfig `
  --name cdo-eks-cluster-dev `
  --region ap-southeast-1

kubectl get nodes -o wide
kubectl get pods -A
```

Ket qua mong doi:

- Node group Ready.
- Pods nen tang trong `argocd`, `kyverno`, `monitoring`, `kube-system` Running hoac Completed.

## 6. Build Va Push CDO Executor Image

```powershell
cd D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS

$repo = terraform -chdir=infra\envs\dev output -raw ecr_executor_url
$tag = "deploy-$(Get-Date -Format yyyyMMdd-HHmmss)"
$registry = ($repo -split "/")[0]
$pw = aws ecr get-login-password --region ap-southeast-1

docker login --username AWS --password $pw $registry

$executorImage = "${repo}:${tag}"
docker build --platform linux/amd64 -t $executorImage .\executor
docker push $executorImage
```

Verify image:

```powershell
aws ecr describe-images `
  --repository-name cdo-executor `
  --region ap-southeast-1 `
  --image-ids imageTag=$tag
```

## 7. Build Va Push Real AI Engine Image

Khong dung `k8s\02-mock-ai.yaml` cho production demo nua. CDO executor hien tro
toi real AI Engine service:

```text
http://ai-engine.self-heal-system.svc.cluster.local:8080
```

Neu team CD da co ECR repo rieng cho AI Engine thi dung repo do. Neu chua co,
tao ECR repo mot lan:

```powershell
aws ecr create-repository `
  --repository-name tf3-cdo02/ai-engine `
  --region ap-southeast-1
```

Build/push tu repo AI Engine:

```powershell
cd D:\Xbrain\Phase2\Capstone-Phase-2-Code\tf-3\ai\ai-engine\detect_decide_verify

$env:AWS_REGION = "ap-southeast-1"
$env:AWS_ACCOUNT_ID = "593777010472"
$aiRepo = "$env:AWS_ACCOUNT_ID.dkr.ecr.$env:AWS_REGION.amazonaws.com/tf3-cdo02/ai-engine"
$aiTag = "deploy-$(Get-Date -Format yyyyMMdd-HHmmss)"
$registry = "$env:AWS_ACCOUNT_ID.dkr.ecr.$env:AWS_REGION.amazonaws.com"
$pw = aws ecr get-login-password --region $env:AWS_REGION

docker login --username AWS --password $pw $registry
docker build --platform linux/amd64 -t "${aiRepo}:${aiTag}" .
docker push "${aiRepo}:${aiTag}"
```

Cap nhat image trong `manifests/ai-engine/deployment.yaml` truoc khi apply:

```yaml
image: 593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ai-engine:<AI_TAG>
```

AI Engine chay rule-based mac dinh:

```yaml
USE_LLM_DECISION=false
USE_LLM_FAULT_TYPE=false
PLATFORM_PROFILE_PATH=/app/config/platform_profile_cdo.json
```

## 8. Build Va Push Ecommerce Demo App Images

Demo app moi nam o repo rieng:

```powershell
cd D:\Xbrain\Phase2\react-ecommerce
docker info

$env:AWS_REGION = "ap-southeast-1"
$env:AWS_ACCOUNT_ID = "593777010472"
$env:IMAGE_TAG = "demo-$(Get-Date -Format yyyyMMdd-HHmmss)"
& "D:\Program Files\Git\bin\bash.exe" scripts/ecr-build-push.sh
```

Images mong doi:

```text
593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ecommerce-api:<IMAGE_TAG>
593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ecommerce-web:<IMAGE_TAG>
```

Render manifest tu demo repo sang CDO repo:

```powershell
cd D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS

$apiImage = "593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ecommerce-api:<IMAGE_TAG>"
$webImage = "593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ecommerce-web:<IMAGE_TAG>"

powershell -ExecutionPolicy Bypass -File .\scripts\render-ecommerce-demo-manifests.ps1 `
  -ApiImage $apiImage `
  -WebImage $webImage
```

Script se tao/cap nhat:

```text
manifests/workloads/ecommerce-api-tenant-a.yaml
manifests/workloads/ecommerce-api-tenant-b.yaml
manifests/workloads/ecommerce-web-tenant-a.yaml
manifests/workloads/ecommerce-web-tenant-b.yaml
```

## 9. Database Secret Cho Ecommerce API

`ecommerce-api` readiness probe goi DB. Neu thieu Secret hoac DB chua reachable,
rollout se fail o `/ready`.

Dung file mau trong ecommerce repo:

```text
D:\Xbrain\Phase2\react-ecommerce\manifests\secrets\ecommerce-db-tenant-a.example.yaml
D:\Xbrain\Phase2\react-ecommerce\manifests\secrets\ecommerce-db-tenant-b.example.yaml
```

Tao ban Secret that, cap nhat `DATABASE_URL`, roi apply:

```powershell
kubectl apply -f <tenant-a-db-secret.yaml>
kubectl apply -f <tenant-b-db-secret.yaml>
```

Neu database moi, chay migration/seed job cua ecommerce repo truoc khi expect
`ecommerce-api` Ready.

## 10. Apply Kubernetes Manifests

Lay output Terraform:

```powershell
cd D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS

$executorImage = "593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/cdo-executor:<EXECUTOR_TAG>"
$role = terraform -chdir=infra\envs\dev output -raw executor_role_arn
$audit = terraform -chdir=infra\envs\dev output -raw audit_bucket_name
```

Apply namespace, RBAC, Kyverno, NetworkPolicy:

```powershell
kubectl apply -f manifests\namespaces\

(Get-Content k8s\01-rbac.yaml -Raw).
  Replace("REPLACE_WITH_EXECUTOR_ROLE_ARN", $role) |
  kubectl apply -f -

kubectl apply -f manifests\rbac\ai-engine-serviceaccount.yaml
kubectl apply -f manifests\kyverno\policies\
kubectl apply -f manifests\networkpolicies\
```

Apply real AI Engine:

```powershell
kubectl apply -f manifests\ai-engine\platform-profile-configmap.yaml
kubectl apply -f manifests\ai-engine\service.yaml
kubectl apply -f manifests\ai-engine\deployment.yaml
kubectl apply -f manifests\ai-engine\hpa.yaml
kubectl apply -f manifests\ai-engine\networkpolicy.yaml
```

Apply CDO executor. Neu dung `k8s\03-executor.yaml`, thay image va audit bucket:

```powershell
(Get-Content k8s\03-executor.yaml -Raw).
  Replace("REPLACE_WITH_ECR_URL:latest", $executorImage).
  Replace("REPLACE_WITH_AUDIT_BUCKET", $audit) |
  kubectl apply -f -
```

Khong apply `k8s\02-mock-ai.yaml` trong demo nay.

Apply ecommerce workload va ServiceMonitor:

```powershell
kubectl apply -f manifests\workloads\ecommerce-api-tenant-a.yaml
kubectl apply -f manifests\workloads\ecommerce-api-tenant-b.yaml
kubectl apply -f manifests\workloads\ecommerce-web-tenant-a.yaml
kubectl apply -f manifests\workloads\ecommerce-web-tenant-b.yaml
kubectl apply -f manifests\observability\servicemonitor-ecommerce-demo.yaml
kubectl apply -f manifests\observability\prometheus-rule-service-signals.yaml
```

Verify rollout:

```powershell
kubectl rollout status deploy/ai-engine -n self-heal-system --timeout=180s
kubectl rollout status deploy/cdo-executor -n self-heal-system --timeout=180s

kubectl rollout status deploy/ecommerce-api -n tenant-a --timeout=180s
kubectl rollout status deploy/ecommerce-web -n tenant-a --timeout=180s
kubectl rollout status deploy/ecommerce-api -n tenant-b --timeout=180s
kubectl rollout status deploy/ecommerce-web -n tenant-b --timeout=180s

kubectl get pods -n self-heal-system
kubectl get deploy,svc,pod -n tenant-a
kubectl get deploy,svc,pod -n tenant-b
kubectl get servicemonitor -n monitoring
```

## 11. Dang Ky Workload Vao ArgoCD

Sau khi ArgoCD Helm release da chay, apply AppProject va Application:

```powershell
kubectl apply -f manifests\argocd\
```

Hai Application hien include ca sample va ecommerce manifests:

```yaml
path: manifests/workloads
directory:
  include: "{tenant-a-sample-app.yaml,ecommerce-api-tenant-a.yaml,ecommerce-web-tenant-a.yaml}"
```

Tenant B tuong tu:

```yaml
include: "{tenant-b-sample-app.yaml,ecommerce-api-tenant-b.yaml,ecommerce-web-tenant-b.yaml}"
```

Verify:

```powershell
kubectl get appprojects.argoproj.io -n argocd
kubectl get applications.argoproj.io -n argocd
```

Ket qua mong doi:

```text
tenant-a-workloads   Synced   Healthy
tenant-b-workloads   Synced   Healthy
```

Neu da apply workload thu cong truoc khi ArgoCD sync, xem muc loi immutable
selector phia duoi.

## 12. Final Verification

Terraform:

```powershell
terraform -chdir=infra\envs\dev plan -detailed-exitcode
```

Kubernetes:

```powershell
kubectl get nodes
kubectl get pods -A
kubectl get clusterpolicies
```

Helm:

```powershell
helm status kyverno -n kyverno
helm status argocd -n argocd
helm status kube-prometheus-stack -n monitoring
helm status opentelemetry-collector -n monitoring
```

AI Engine:

```powershell
kubectl get deploy,svc,pod -n self-heal-system
kubectl port-forward -n self-heal-system svc/ai-engine 8080:8080
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
```

Ecommerce API:

```powershell
kubectl port-forward -n tenant-a svc/ecommerce-api 3000:3000
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/ready
curl http://127.0.0.1:3000/metrics
```

PromQL check sau khi Prometheus scrape ServiceMonitor:

```promql
(
  (sum(rate(http_requests_total{deployment="ecommerce-api",code=~"5.."}[1m])) or vector(0))
  +
  (sum(rate(http_requests_total{deployment="ecommerce-api",status=~"5.."}[1m])) or vector(0))
)
/
sum(rate(http_requests_total{deployment="ecommerce-api"}[1m]))
```

Audit Object Lock:

```powershell
aws s3api get-object-lock-configuration `
  --bucket cdo-audit-593777010472-cdo-eks-cluster-dev-dev `
  --region ap-southeast-1
```

## 13. Demo Self-Heal Voi Ecommerce App

### 13.1. Kiem Tra Executor Watch Mode

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system --tail=30
```

Log mong doi:

```text
[watcher] poll=15s cooldown=300s namespaces=['tenant-a', 'tenant-b']
```

Neu can ep executor sang watch mode:

```powershell
kubectl set env deploy/cdo-executor -n self-heal-system `
  CDO_POLL_INTERVAL_S=15 `
  CDO_VERIFY_MAX_WAIT_S=5 `
  AI_BASE_URL=http://ai-engine.self-heal-system.svc.cluster.local:8080 `
  CDO_K8S_MOCK=false

kubectl patch deploy/cdo-executor -n self-heal-system --type=json `
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/command","value":["python","main.py","--watch"]}]'

kubectl rollout status deploy/cdo-executor -n self-heal-system --timeout=180s
```

### 13.2. Validate Metrics Va Fault Injection Endpoint

```powershell
kubectl port-forward -n tenant-a svc/ecommerce-api 3000:3000

curl http://127.0.0.1:3000/metrics

curl -X POST http://127.0.0.1:3000/debug/fault/error-rate `
  -H "Content-Type: application/json" `
  -d "{\"error_rate\":0.5}"
```

Luu y: error-rate fault giup verify `service_error_rate`, log JSON, va
Prometheus scrape. Executor `--watch` hien tu dong bat loi tu Kubernetes pod
state. Neu chua bat Alertmanager/webhook path, error-rate khong tu dong tao
incident cho CDO; dung no nhu telemetry validation hoac manual scenario.

Reset fault injection:

```powershell
curl -X POST http://127.0.0.1:3000/debug/fault/reset
```

### 13.3. Demo Auto-Heal Chac Chan Bang OOM Tren Ecommerce API

Mo log executor o mot terminal:

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system -f
```

O terminal khac, gay OOM that tren `ecommerce-api` tenant-a:

```powershell
kubectl set resources deploy/ecommerce-api -n tenant-a -c ecommerce-api `
  --limits=memory=64Mi `
  --requests=memory=64Mi
```

Theo doi:

```powershell
kubectl get pods -n tenant-a -w
kubectl describe pod -n tenant-a -l app=ecommerce-api
```

Luong mong doi:

1. `cdo-executor` chay `python main.py --watch`.
2. Watcher poll namespace `tenant-a,tenant-b`.
3. Kubernetes ghi `OOMKilled` hoac `lastState.terminated.exitCode=137`.
4. `watcher.py` map thanh `pod_oom_event` va `OOM_KILL`.
5. Executor goi real AI Engine `/v1/detect`, `/v1/decide`, `/v1/verify`.
6. AI Engine tra runbook/action plan tu platform profile.
7. Safety gate kiem tra namespace/action/blast radius.
8. Urgent executor dry-run roi patch Deployment neu action duoc allow.
9. Audit ghi stdout va S3; idempotency ghi DynamoDB.

Nghiem thu:

```powershell
kubectl rollout status deploy/ecommerce-api -n tenant-a --timeout=180s
kubectl get deploy ecommerce-api -n tenant-a `
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
kubectl logs deploy/cdo-executor -n self-heal-system --since=10m
```

Tim cac event/log dang nay:

```text
[watcher] phat hien OOM_KILL tai tenant-a/ecommerce-api
detect_called
action_plan_received
safety_passed
execute_done
verify_done
incident_closed
```

Reset resource sau demo:

```powershell
kubectl set resources deploy/ecommerce-api -n tenant-a -c ecommerce-api `
  --limits=memory=512Mi `
  --requests=memory=256Mi

kubectl rollout status deploy/ecommerce-api -n tenant-a --timeout=180s
```

### 13.4. Nghiem Thu Audit Va Idempotency

Audit S3:

```powershell
$audit = terraform -chdir=infra\envs\dev output -raw audit_bucket_name
aws s3 ls "s3://$audit/audit/" --recursive --region ap-southeast-1
```

Doc mot object audit moi:

```powershell
aws s3 cp "s3://$audit/audit/<tenant_id>/<correlation_id>.json" - --region ap-southeast-1
```

DynamoDB:

```powershell
aws dynamodb scan `
  --table-name cdo-idempotency-dev `
  --region ap-southeast-1 `
  --max-items 5
```

## Loi Thuong Gap Va Cach Sua

### 1. Account Cu Khong Dung Voi Deploy Moi

Hien tuong:

- Docs/code cu tro account khac.
- AWS CLI hien tai la `593777010472`.

Cach sua:

- Chot account deploy bang `aws sts get-caller-identity`.
- Doi backend bucket va `aws_account_id`.
- Bootstrap state bucket moi.

### 2. Audit S3 Bucket Name Qua Chung Lam Terraform Treo

Hien tuong:

- `module.audit.aws_s3_bucket.audit` treo lau.
- `head-bucket` voi ten bucket cu tra `404`.

Cach sua:

Dung bucket co account id:

```hcl
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "audit" {
  bucket              = "cdo-audit-${data.aws_caller_identity.current.account_id}-${var.cluster_name}-${var.environment}"
  force_destroy       = false
  object_lock_enabled = true
}
```

### 3. State Lock Con Lai Sau Khi Dung Terraform Process

Hien tuong:

```text
Error acquiring the state lock
PreconditionFailed
Lock Info ID: <LOCK_ID>
```

Cach sua:

Chi force-unlock neu chac chan lock la cua session vua bi dung:

```powershell
terraform -chdir=infra\envs\dev force-unlock -force <LOCK_ID>
```

Sau do plan/apply lai.

### 4. OTel Chart Yeu Cau `image.repository`

Hien tuong:

```text
[ERROR] 'image.repository' must be set
```

Cach sua trong `infra/modules/observability/main.tf`:

```hcl
image = {
  repository = "ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-k8s"
}
command = {
  name = "otelcol-k8s"
}
```

Dong thoi doi exporter cu `logging` sang `debug`.

### 5. Kyverno Cleanup Job ImagePullBackOff

Hien tuong:

```text
Failed to pull image "bitnami/kubectl:1.28.5"
```

Cach sua: disable cleanup jobs trong `infra/modules/kyverno/main.tf`, roi apply
Terraform lai:

```hcl
set {
  name  = "policyReportsCleanup.enabled"
  value = "false"
}
```

Ap dung tuong tu cho cac `cleanupJobs.*.enabled`.

### 6. Docker Daemon Chua Chay

Hien tuong:

```text
open //./pipe/docker_engine: The system cannot find the file specified
```

Cach sua:

```powershell
Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe" -WindowStyle Hidden
Start-Sleep -Seconds 20
docker info
```

Neu `docker info` tra loi 500, doi them 20-30 giay roi chay lai.

### 7. Executor CrashLoopBackOff Vi Chay Scenario Runner Trong Deployment

Hien tuong:

- Pod executor CrashLoopBackOff.
- Log bao scenario runner fail vi deployment trong scenario khong ton tai.

Cach sua:

Deployment runtime phai chay watch mode:

```yaml
command: ["python", "main.py", "--watch"]
```

Env can co:

```yaml
AI_BASE_URL=http://ai-engine.self-heal-system.svc.cluster.local:8080
CDO_K8S_MOCK=false
CDO_TENANT_NAMESPACES=tenant-a,tenant-b
CDO_POLL_INTERVAL_S=15
CDO_VERIFY_MAX_WAIT_S=5
```

### 8. Van Apply Mock AI Server

Hien tuong:

- `ai-engine` pod chay image executor va command `python mock_ai_server.py`.
- CDO khong goi real detect/decide/verify engine.

Cach sua:

- Khong apply `k8s\02-mock-ai.yaml`.
- Apply `manifests\ai-engine\platform-profile-configmap.yaml`.
- Apply `manifests\ai-engine\deployment.yaml`, `service.yaml`, `hpa.yaml`,
  `networkpolicy.yaml`.
- Dam bao image trong deployment la AI Engine image that, khong phai executor image.

### 9. AI Engine Image Van La `ai-engine:replace-me`

Hien tuong:

```text
ErrImagePull / ImagePullBackOff
```

Cach sua:

- Build/push AI Engine image len ECR.
- Sua `manifests/ai-engine/deployment.yaml`:

```yaml
image: 593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/tf3-cdo02/ai-engine:<AI_TAG>
```

Apply lai va rollout:

```powershell
kubectl apply -f manifests\ai-engine\deployment.yaml
kubectl rollout status deploy/ai-engine -n self-heal-system --timeout=180s
```

### 10. Ecommerce API Khong Ready Vi Thieu DB Secret

Hien tuong:

- `ecommerce-api` pod Running nhung `READY 0/1`.
- `/ready` fail.
- Event/log lien quan Secret `ecommerce-db` hoac DB connection.

Cach sua:

- Tao Secret `ecommerce-db` cho ca `tenant-a` va `tenant-b`.
- Cap nhat `DATABASE_URL` dung RDS/Postgres endpoint.
- Chay migration/seed neu DB moi.
- Rollout lai `ecommerce-api`.

### 11. Service Error Rate Khong Co Data

Hien tuong:

- `/metrics` co `http_requests_total{status="500"}`.
- PromQL cu filter `code=~"5.."` nen khong ra data.

Cach sua:

- CDO collector va PrometheusRule phai support ca `code` va `status`.
- Apply `manifests/observability/prometheus-rule-service-signals.yaml`.
- ServiceMonitor ecommerce chi scrape `service=ecommerce-api` vi web app khong co `/metrics`.

### 12. ArgoCD UI Trong Vi Chua Tao Application

Hien tuong:

```powershell
kubectl get applications.argoproj.io -A
```

tra:

```text
No resources found
```

Cach sua:

```powershell
kubectl apply -f manifests\argocd\
kubectl get applications.argoproj.io -n argocd
```

### 13. AppProject Bi Reject Vi Field `spec.syncPolicy`

Hien tuong:

```text
strict decoding error: unknown field "spec.syncPolicy"
```

Cach sua:

- Xoa `spec.syncPolicy` khoi `AppProject`.
- `syncPolicy` chi nam trong `Application`.

### 14. ArgoCD Sync Fail Vi Deployment Selector Immutable

Hien tuong:

```text
Deployment.apps "<name>" is invalid:
spec.selector: Invalid value ... field is immutable
```

Nguyen nhan:

- Workload da duoc apply thu cong bang manifest cu.
- ArgoCD sync manifest moi co selector khac.

Cach sua:

Voi sample workload cu:

```powershell
kubectl delete deploy cdo-sample-api -n tenant-a --ignore-not-found=true
kubectl delete deploy notification-service -n tenant-b --ignore-not-found=true
kubectl delete svc checkout-svc -n tenant-a --ignore-not-found=true
kubectl delete svc notification-svc -n tenant-b --ignore-not-found=true
```

Voi ecommerce workload:

```powershell
kubectl delete deploy ecommerce-api -n tenant-a --ignore-not-found=true
kubectl delete deploy ecommerce-web -n tenant-a --ignore-not-found=true
kubectl delete deploy ecommerce-api -n tenant-b --ignore-not-found=true
kubectl delete deploy ecommerce-web -n tenant-b --ignore-not-found=true
```

Refresh ArgoCD:

```powershell
kubectl annotate application tenant-a-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
kubectl annotate application tenant-b-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
```

### 15. PowerShell Quoting/JsonPath Loi

Hien tuong:

- `kubectl describe ... --tail` fail vi `describe` khong co flag `--tail`.
- JsonPath bi PowerShell escape sai.

Cach sua:

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system --tail=20
kubectl get deploy ecommerce-api -n tenant-a -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
```

## Cleanup Khi Khong Can Ha Tang Nua

Ha tang nay co EKS, NAT Gateway va node group nen se phat sinh chi phi. Khi demo
xong:

```powershell
terraform -chdir=infra\envs\dev destroy
```

Luu y:

- Audit bucket bat Object Lock Governance 90 ngay va `force_destroy=false`; destroy
  co the khong xoa het bucket neu co object audit bi retention.
- Neu destroy fail vi resource con data, xu ly dung resource do roi chay destroy
  lai.
- Sau destroy nen verify bang AWS API, khong chi tin local state.
