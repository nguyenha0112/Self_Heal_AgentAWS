# Fresh Infra Deploy Runbook

Tài liệu này ghi lại các bước đã chạy để deploy mới hoàn toàn hạ tầng trong `infra/` trên AWS account hiện tại, không dùng account cũ. Phần cuối có thêm hướng dẫn demo self-heal ở chế độ production `--watch`, luồng hoạt động và cách nghiệm thu.

## Thông tin lần deploy này

- AWS account: `593777010472`
- Region: `ap-southeast-1`
- Terraform state bucket: `cdo-tf-state-593777010472-ap-southeast-1-dev`
- Terraform state key: `envs/dev/terraform.tfstate`
- EKS cluster: `cdo-eks-cluster-dev`
- ECR repo: `593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/cdo-executor`
- Image đã push: `593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/cdo-executor:deploy-20260630-170855`
- Audit bucket: `cdo-audit-593777010472-cdo-eks-cluster-dev-dev`
- Executor IRSA role: `arn:aws:iam::593777010472:role/cdo-executor-irsa-cdo-eks-cluster-dev`

## 1. Kiểm tra tool và AWS identity

Chạy từ root repo:

```powershell
aws sts get-caller-identity
aws configure get region
terraform version
kubectl version --client=true
helm version
docker --version
```

Yêu cầu:

- Terraform `>= 1.10`
- AWS CLI đang trỏ đúng account deploy mới
- Region deploy là `ap-southeast-1`
- Docker Desktop/daemon phải chạy trước bước build image

## 2. Cập nhật account mới trong Terraform

Sửa `infra/envs/dev/providers.tf`:

```hcl
backend "s3" {
  bucket       = "cdo-tf-state-593777010472-ap-southeast-1-dev"
  key          = "envs/dev/terraform.tfstate"
  region       = "ap-southeast-1"
  use_lockfile = true
  encrypt      = true
}
```

Sửa `infra/envs/dev/variables.tf`:

```hcl
variable "aws_account_id" { default = "593777010472" }
```

## 3. Bootstrap S3 remote state

Chỉ cần làm một lần cho account/region mới.

```powershell
terraform -chdir=infra\bootstrap init
terraform -chdir=infra\bootstrap apply -auto-approve
```

Kiểm tra bucket:

```powershell
aws s3api head-bucket `
  --bucket cdo-tf-state-593777010472-ap-southeast-1-dev `
  --region ap-southeast-1
```

## 4. Init, plan, apply Terraform env dev

Thêm Helm repo cache trước khi apply:

```powershell
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
```

Chạy Terraform:

```powershell
terraform -chdir=infra\envs\dev init -reconfigure
terraform -chdir=infra\envs\dev validate
terraform -chdir=infra\envs\dev plan "-out=tfplan-dev.out"
terraform -chdir=infra\envs\dev apply tfplan-dev.out
```

Verify Terraform:

```powershell
terraform -chdir=infra\envs\dev plan -detailed-exitcode
terraform -chdir=infra\envs\dev output
```

Kết quả mong đợi: `No changes`.

## 5. Update kubeconfig và verify EKS

```powershell
aws eks update-kubeconfig `
  --name cdo-eks-cluster-dev `
  --region ap-southeast-1

kubectl get nodes -o wide
kubectl get pods -A
```

Kết quả mong đợi:

- 2 node `Ready`
- Pods trong `argocd`, `kyverno`, `monitoring`, `kube-system` Running

## 6. Build và push executor image

Nếu Docker daemon chưa chạy, mở Docker Desktop trước:

```powershell
Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe" -WindowStyle Hidden
Start-Sleep -Seconds 20
docker info
```

Build và push:

```powershell
$repo = terraform -chdir=infra\envs\dev output -raw ecr_executor_url
$tag = "deploy-$(Get-Date -Format yyyyMMdd-HHmmss)"
$registry = ($repo -split "/")[0]
$pw = aws ecr get-login-password --region ap-southeast-1

docker login --username AWS --password $pw $registry

$image = "${repo}:${tag}"
docker build --platform linux/amd64 -t $image .\executor
docker push $image
```

Kiểm tra image:

```powershell
aws ecr describe-images `
  --repository-name cdo-executor `
  --region ap-southeast-1 `
  --image-ids imageTag=<TAG>
```

## 7. Apply Kubernetes manifests

Lấy output Terraform:

```powershell
$image = "593777010472.dkr.ecr.ap-southeast-1.amazonaws.com/cdo-executor:<TAG>"
$role = terraform -chdir=infra\envs\dev output -raw executor_role_arn
$audit = terraform -chdir=infra\envs\dev output -raw audit_bucket_name
```

Apply namespace, RBAC, workloads, Kyverno policies, NetworkPolicy, mock AI, executor:

```powershell
kubectl apply -f manifests\namespaces\

(Get-Content k8s\01-rbac.yaml -Raw).
  Replace("REPLACE_WITH_EXECUTOR_ROLE_ARN", $role) |
  kubectl apply -f -

kubectl apply -f k8s\04-workloads.yaml
kubectl apply -f manifests\kyverno\policies\
kubectl apply -f manifests\networkpolicies\

(Get-Content k8s\02-mock-ai.yaml -Raw).
  Replace("REPLACE_WITH_ECR_URL:latest", $image) |
  kubectl apply -f -

(Get-Content k8s\03-executor.yaml -Raw).
  Replace("REPLACE_WITH_ECR_URL:latest", $image).
  Replace("REPLACE_WITH_AUDIT_BUCKET", $audit) |
  kubectl apply -f -
```

Verify rollout:

```powershell
kubectl rollout status deploy/ai-engine -n self-heal-system --timeout=180s
kubectl rollout status deploy/cdo-executor -n self-heal-system --timeout=180s
kubectl get pods -n self-heal-system
kubectl get pods -n tenant-a
kubectl get pods -n tenant-b
kubectl get clusterpolicies
```

## 8. Đăng ký workload vào ArgoCD

Sau khi ArgoCD Helm release đã chạy, cần tạo `AppProject` và `Application` thì UI ArgoCD mới có app để hiển thị. Nếu chỉ cài ArgoCD control plane mà chưa apply các manifest này, màn hình Applications sẽ trống.

Manifest dùng:

```text
manifests/argocd/appproject-tenant-a.yaml
manifests/argocd/appproject-tenant-b.yaml
manifests/argocd/application-tenant-a.yaml
manifests/argocd/application-tenant-b.yaml
```

Hai `Application` trỏ tới GitHub repo:

```yaml
repoURL: https://github.com/nguyenha0112/Self_Heal_AgentAWS.git
targetRevision: HEAD
path: manifests/workloads
directory:
  include: tenant-a-sample-app.yaml
```

Tenant B tương tự nhưng `include: tenant-b-sample-app.yaml`.

Apply ArgoCD manifests:

```powershell
kubectl apply -f manifests\argocd\
```

Nếu workload trước đó đã được apply thủ công bằng `k8s\04-workloads.yaml`, có thể gặp lỗi immutable selector khi ArgoCD sync. Cách xử lý là xoá Deployment mẫu cũ để ArgoCD tạo lại theo manifest GitOps:

```powershell
kubectl delete deploy cdo-sample-api -n tenant-a --ignore-not-found=true
kubectl delete deploy notification-service -n tenant-b --ignore-not-found=true

kubectl annotate application tenant-a-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
kubectl annotate application tenant-b-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
```

Nếu còn Service cũ từ manifest thủ công, xoá để tránh nhầm lẫn:

```powershell
kubectl delete svc checkout-svc -n tenant-a --ignore-not-found=true
kubectl delete svc notification-svc -n tenant-b --ignore-not-found=true
```

Verify ArgoCD:

```powershell
kubectl get appprojects.argoproj.io -n argocd
kubectl get applications.argoproj.io -n argocd
kubectl get deploy,svc -n tenant-a
kubectl get deploy,svc -n tenant-b
```

Kết quả mong đợi:

```text
NAME                 SYNC STATUS   HEALTH STATUS
tenant-a-workloads   Synced        Healthy
tenant-b-workloads   Synced        Healthy
```

Sau đó refresh UI ArgoCD tại `http://localhost:8080/applications`; sẽ thấy 2 app `tenant-a-workloads` và `tenant-b-workloads`.

## 9. Final verification

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

Audit Object Lock:

```powershell
aws s3api get-object-lock-configuration `
  --bucket cdo-audit-593777010472-cdo-eks-cluster-dev-dev `
  --region ap-southeast-1
```

Kết quả mong đợi:

- Terraform: `No changes`
- Helm releases: `STATUS: deployed`
- Pods: Running
- ArgoCD Applications: `Synced`, `Healthy`
- Audit bucket: `ObjectLockEnabled=Enabled`, `Mode=GOVERNANCE`, `Days=90`

## 10. Demo self-heal production `--watch`

### 10.1. Kiểm tra trạng thái trước demo

Executor hiện nên chạy ở watch mode:

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system --tail=20
```

Log mong đợi:

```text
[watcher] poll=15s cooldown=300s namespaces=['tenant-a', 'tenant-b']
```

Kiểm tra pod và workload mẫu:

```powershell
kubectl get pods -n self-heal-system
kubectl get pods -n tenant-a
kubectl get deploy cdo-sample-api -n tenant-a -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
```

Nếu cần ép lại executor sang watch mode:

```powershell
kubectl set env deploy/cdo-executor -n self-heal-system `
  CDO_POLL_INTERVAL_S=15 `
  CDO_VERIFY_MAX_WAIT_S=5

kubectl patch deploy/cdo-executor -n self-heal-system --type=json `
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/command","value":["python","main.py","--watch"]}]'

kubectl rollout status deploy/cdo-executor -n self-heal-system --timeout=180s
```

### 10.2. Mở log executor ở một terminal riêng

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system -f
```

Để dừng follow log: nhấn `Ctrl+C`.

### 10.3. Gây lỗi OOM thật trên workload tenant-a

Chạy ở terminal khác:

```powershell
kubectl set resources deploy/cdo-sample-api -n tenant-a -c podinfo `
  --limits=memory=8Mi `
  --requests=memory=8Mi
```

Theo dõi pod bị restart/OOM:

```powershell
kubectl get pods -n tenant-a -w
```

Hoặc xem trạng thái pod sau vài chục giây:

```powershell
kubectl describe pod -n tenant-a -l app=checkout-svc
```

Nếu workload đã được ArgoCD recreate theo GitOps manifest, label pod là `app=cdo-sample-api`, nên lệnh describe có thể dùng:

```powershell
kubectl describe pod -n tenant-a -l app=cdo-sample-api
```

### 10.4. Luồng hoạt động của demo

Luồng thực tế trong code:

1. `cdo-executor` chạy `python main.py --watch`.
2. Watcher poll pod trong `tenant-a,tenant-b` mỗi `CDO_POLL_INTERVAL_S=15` giây.
3. Khi `cdo-sample-api` bị OOM, Kubernetes ghi trạng thái container `OOMKilled` hoặc `lastState.terminated.exitCode=137`.
4. `watcher.py` map lỗi đó thành telemetry signal `pod_oom_event` và fault type `OOM_KILL`.
5. Executor gọi mock AI service qua `AI_BASE_URL`.
6. Mock AI detect ra scenario `oom_kill`, decide action `PATCH_MEMORY_LIMIT`, target `deployment/cdo-sample-api`, memory limit `1024Mi`.
7. Pre-decide gate và safety gate kiểm tra confidence, namespace, action allow-list và giới hạn memory tối đa.
8. Urgent executor chạy server-side dry-run trước, sau đó patch thật Deployment bằng Kubernetes API.
9. Executor chờ tối đa `CDO_VERIFY_MAX_WAIT_S=5` giây, scrape lại telemetry, gọi `/v1/verify`.
10. Nếu verify trả `DONE`, incident được đóng với kết quả `auto_resolved`.
11. Audit event được in ra stdout và flush thành object trong S3 theo key `audit/<tenant_id>/<correlation_id>.json`.
12. Idempotency key được ghi vào DynamoDB table `cdo-idempotency-dev` để tránh xử lý trùng cùng incident.

### 10.5. Cách nghiệm thu kết quả

Nghiệm thu Kubernetes patch:

```powershell
kubectl get deploy cdo-sample-api -n tenant-a `
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
```

Kết quả mong đợi:

```text
1024Mi
```

Kubernetes có thể hiển thị tương đương là `1Gi`.

Nghiệm thu rollout:

```powershell
kubectl rollout status deploy/cdo-sample-api -n tenant-a --timeout=180s
kubectl get pods -n tenant-a
```

Kết quả mong đợi: pod mới `Running`, `READY 1/1`.

Nghiệm thu log executor:

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system --since=10m
```

Các event/log cần thấy:

```text
[watcher] phát hiện OOM_KILL tại tenant-a/cdo-sample-api
action_plan_received ... "action_type":"PATCH_MEMORY_LIMIT"
safety_passed
execute_done ... "result":"success"
verify_done ... "next_action":"DONE"
incident_closed ... "result":"auto_resolved"
```

Nghiệm thu audit S3:

```powershell
$audit = terraform -chdir=infra\envs\dev output -raw audit_bucket_name
aws s3 ls "s3://$audit/audit/" --recursive --region ap-southeast-1
```

Lấy một object audit mới nhất rồi đọc nội dung:

```powershell
aws s3 cp "s3://$audit/audit/<tenant_id>/<correlation_id>.json" - --region ap-southeast-1
```

Trong JSON audit cần thấy chuỗi event tương ứng với `detect_called`, `action_plan_received`, `safety_passed`, `execute_done`, `verify_done`, `incident_closed`.

Nghiệm thu DynamoDB idempotency:

```powershell
aws dynamodb scan `
  --table-name cdo-idempotency-dev `
  --region ap-southeast-1 `
  --max-items 5
```

Kết quả mong đợi: có item chứa `idempotency_key` và `expires_at`. Nếu chạy lại cùng incident trong thời gian TTL, executor có thể log `idempotency_duplicate_denied`.

### 10.6. Reset workload sau demo

Đưa workload mẫu về mức ban đầu:

```powershell
kubectl set resources deploy/cdo-sample-api -n tenant-a -c podinfo `
  --limits=memory=128Mi `
  --requests=memory=64Mi

kubectl rollout status deploy/cdo-sample-api -n tenant-a --timeout=180s
```

## Lỗi đã gặp và cách sửa

### 1. Account cũ không đúng với deploy mới

Hiện tượng:

- Docs cũ trỏ account `012619468490`
- Code Terraform ban đầu trỏ `938145531618`
- AWS CLI hiện tại là `593777010472`

Cách sửa:

- Chốt deploy fresh trên account `593777010472`
- Đổi S3 backend bucket và `aws_account_id`
- Bootstrap state bucket mới theo account hiện tại

### 2. Audit S3 bucket name quá chung làm Terraform treo

Hiện tượng:

- `module.audit.aws_s3_bucket.audit` treo hơn 20 phút
- `aws s3api head-bucket --bucket cdo-audit-cdo-eks-cluster-dev-dev` trả `404`

Nguyên nhân:

- Tên bucket S3 là global. Tên `cdo-audit-cdo-eks-cluster-dev-dev` quá chung, không an toàn cho multi-account fresh deploy.

Cách sửa:

Thêm account ID vào tên audit bucket trong `infra/modules/audit/main.tf`:

```hcl
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "audit" {
  bucket        = "cdo-audit-${data.aws_caller_identity.current.account_id}-${var.cluster_name}-${var.environment}"
  force_destroy = false

  object_lock_enabled = true
}
```

### 3. State lock còn lại sau khi dừng Terraform process

Hiện tượng:

```text
Error acquiring the state lock
PreconditionFailed
Lock Info ID: <LOCK_ID>
```

Cách sửa:

Chỉ force unlock nếu chắc chắn lock là của session apply vừa bị dừng trên máy mình:

```powershell
terraform -chdir=infra\envs\dev force-unlock -force <LOCK_ID>
```

Sau đó chạy lại:

```powershell
terraform -chdir=infra\envs\dev plan "-out=tfplan-dev-2.out"
terraform -chdir=infra\envs\dev apply tfplan-dev-2.out
```

### 4. OTel chart yêu cầu `image.repository`

Hiện tượng:

```text
Error: execution error at (opentelemetry-collector/templates/NOTES.txt:2:3):
[ERROR] 'image.repository' must be set
```

Cách sửa:

Sửa `infra/modules/observability/main.tf`, set image và command:

```hcl
image = {
  repository = "ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-k8s"
}
command = {
  name = "otelcol-k8s"
}
```

Đồng thời đổi exporter cũ `logging` sang `debug` vì chart mới dùng `debug` exporter.

### 5. Kyverno cleanup job ImagePullBackOff

Hiện tượng:

```text
Failed to pull image "bitnami/kubectl:1.28.5"
docker.io/bitnami/kubectl:1.28.5: not found
```

Cách sửa:

Disable các cleanup jobs và post-upgrade cleanup hook trong `infra/modules/kyverno/main.tf`:

```hcl
set {
  name  = "policyReportsCleanup.enabled"
  value = "false"
}

set {
  name  = "cleanupJobs.admissionReports.enabled"
  value = "false"
}

set {
  name  = "cleanupJobs.clusterAdmissionReports.enabled"
  value = "false"
}

set {
  name  = "cleanupJobs.ephemeralReports.enabled"
  value = "false"
}

set {
  name  = "cleanupJobs.clusterEphemeralReports.enabled"
  value = "false"
}
```

Apply lại Terraform. Release Kyverno phải về:

```text
STATUS: deployed
```

### 6. Docker daemon chưa chạy

Hiện tượng:

```text
error during connect:
open //./pipe/docker_engine: The system cannot find the file specified
```

Cách sửa:

Mở Docker Desktop, đợi daemon sẵn sàng:

```powershell
Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe" -WindowStyle Hidden
Start-Sleep -Seconds 20
docker info
```

Nếu lần đầu `docker info` trả 500, đợi thêm 20-30 giây rồi chạy lại.

### 7. Executor CrashLoopBackOff vì chạy `run_scenarios.py` trong Deployment

Hiện tượng:

- Pod `cdo-executor` CrashLoopBackOff
- Log báo scenario runner crash vì deployment trong scenario không tồn tại:

```text
deployments.apps "cdo-orders-api" not found
```

Nguyên nhân:

- `k8s/03-executor.yaml` chạy `python run_scenarios.py`, phù hợp test Job hơn là Deployment dài hạn.

Cách sửa:

Đổi executor Deployment sang watch mode:

```yaml
command: ["python", "main.py", "--watch"]
```

Thêm env:

```yaml
- name: CDO_POLL_INTERVAL_S
  value: "15"
- name: CDO_VERIFY_MAX_WAIT_S
  value: "5"
```

Apply lại manifest executor:

```powershell
(Get-Content k8s\03-executor.yaml -Raw).
  Replace("REPLACE_WITH_ECR_URL:latest", $image).
  Replace("REPLACE_WITH_AUDIT_BUCKET", $audit) |
  kubectl apply -f -

kubectl rollout status deploy/cdo-executor -n self-heal-system --timeout=180s
```

Log mong đợi:

```text
[watcher] poll=15s cooldown=300s namespaces=['tenant-a', 'tenant-b']
```

### 8. PowerShell quoting/jsonpath nhỏ

Hiện tượng:

- `kubectl describe ... --tail` fail vì `describe` không có flag `--tail`
- JsonPath có dấu quote hoặc escape sai có thể bị PowerShell truyền lỗi

Cách xử lý:

- Dùng `kubectl logs ... --tail=N` cho log
- Với JsonPath trên PowerShell, dùng biểu thức đơn giản hoặc tách command:

```powershell
kubectl get deploy cdo-sample-api -n tenant-a -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
kubectl logs deploy/cdo-executor -n self-heal-system --tail=20
```

### 9. ArgoCD UI trống vì chưa tạo Application

Hiện tượng:

- Vào ArgoCD UI thấy `No applications available`.
- Kiểm tra Kubernetes:

```powershell
kubectl get applications.argoproj.io -A
```

trả:

```text
No resources found
```

Nguyên nhân:

- Terraform/Helm mới chỉ cài ArgoCD control plane.
- Chưa apply các manifest `Application` và `AppProject` trong `manifests/argocd`.

Cách sửa:

```powershell
kubectl apply -f manifests\argocd\
kubectl get applications.argoproj.io -n argocd
```

Kết quả cuối cùng sau khi sửa:

```text
NAME                 SYNC STATUS   HEALTH STATUS
tenant-a-workloads   Synced        Healthy
tenant-b-workloads   Synced        Healthy
```

### 10. AppProject bị reject vì field `spec.syncPolicy`

Hiện tượng:

```text
AppProject in version "v1alpha1" cannot be handled as a AppProject:
strict decoding error: unknown field "spec.syncPolicy"
```

Nguyên nhân:

- `syncPolicy` là field của `Application`, không phải field hợp lệ trong `AppProject` schema của ArgoCD v2.13.

Cách sửa:

- Xoá block `spec.syncPolicy` khỏi:
  - `manifests/argocd/appproject-tenant-a.yaml`
  - `manifests/argocd/appproject-tenant-b.yaml`
- Apply lại:

```powershell
kubectl apply -f manifests\argocd\appproject-tenant-a.yaml `
  -f manifests\argocd\appproject-tenant-b.yaml
```

### 11. ArgoCD sync fail vì Deployment selector immutable

Hiện tượng:

```text
Deployment.apps "cdo-sample-api" is invalid:
spec.selector: Invalid value ... field is immutable
```

Tương tự với `notification-service`.

Nguyên nhân:

- Workload mẫu đã được apply thủ công trước đó từ `k8s\04-workloads.yaml`.
- Manifest thủ công dùng selector:
  - tenant-a: `app=checkout-svc`
  - tenant-b: `app=notification-svc`
- Manifest GitOps trong `manifests/workloads` dùng selector:
  - tenant-a: `app=cdo-sample-api`
  - tenant-b: `app=notification-service`
- Kubernetes không cho đổi `spec.selector` của Deployment sau khi đã tạo.

Cách sửa:

Xoá Deployment mẫu cũ để ArgoCD tạo lại theo GitOps source:

```powershell
kubectl delete deploy cdo-sample-api -n tenant-a --ignore-not-found=true
kubectl delete deploy notification-service -n tenant-b --ignore-not-found=true
```

Refresh ArgoCD app:

```powershell
kubectl annotate application tenant-a-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
kubectl annotate application tenant-b-workloads -n argocd `
  argocd.argoproj.io/refresh=hard --overwrite
```

Xoá Service cũ không còn dùng:

```powershell
kubectl delete svc checkout-svc -n tenant-a --ignore-not-found=true
kubectl delete svc notification-svc -n tenant-b --ignore-not-found=true
```

Verify:

```powershell
kubectl get applications.argoproj.io -n argocd
kubectl get deploy,svc -n tenant-a
kubectl get deploy,svc -n tenant-b
```

## Cleanup khi không cần hạ tầng nữa

Hạ tầng này có EKS, NAT Gateway và node group nên sẽ phát sinh chi phí. Khi demo xong:

```powershell
terraform -chdir=infra\envs\dev destroy
```

Lưu ý:

- Audit bucket bật Object Lock Governance 90 ngày và `force_destroy=false`; destroy có thể không xoá hết bucket nếu có object audit bị retention.
- Nếu destroy fail vì resource còn data, xử lý đúng resource đó rồi chạy destroy lại.
- Sau destroy nên verify bằng AWS API, không chỉ tin local state.
