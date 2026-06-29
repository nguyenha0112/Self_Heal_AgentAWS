# CDO-02 Self-Heal — Hướng dẫn Deploy (nhánh `chore/argocd-team-setup`)

Nhánh `chore/argocd-team-setup` là **bản deploy-được**: infra Singapore (chore) + executor có enum-fix (main) + `k8s/` + các hardening. `main` để nguyên (sẽ merge sau khi ổn).

- **AWS account**: `012619468490` · **Region**: `ap-southeast-1` (Singapore)
- **Shared TF state (S3)**: `cdo-tf-state-012619468490-ap-southeast-1-dev`, key `envs/dev/terraform.tfstate`, native S3 lock.
- **Tenant ID**: `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`

---

## 0) Yêu cầu công cụ
| Tool | Ghi chú |
|---|---|
| AWS CLI | `aws configure` đúng account `012619468490`; check `aws sts get-caller-identity` |
| Terraform | **≥ 1.10** (dùng `use_lockfile` S3 native lock) |
| kubectl | tương thích K8s 1.30 |
| helm | **cần cài** để populate repo cache cho terraform-provider-helm (xem mục Troubleshooting) |
| docker | build image executor (linux/amd64) |

> ⚠️ **Quy tắc team (WORK_RULE §IV)**: chỉ **1 người `terraform apply`/`destroy` một lúc** (S3 lock sẽ chặn người thứ 2).

---

## 1) Init Terraform (kết nối state chung)
```bash
cd infra/envs/dev
terraform init                 # tự dùng backend S3 ap-southeast-1
terraform plan                 # xác nhận đọc được state chung
```
Người **đầu tiên** từng tạo bucket state qua `infra/bootstrap/` (1 lần). Người sau chỉ `init`.

## 2) Apply hạ tầng
```bash
# helm repo cache TRƯỚC khi apply (nếu chưa, xem Troubleshooting #1)
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo update

terraform apply                # ~15–20': VPC, EKS 1.30, nodes, IAM/IRSA, audit (S3/DDB/SQS), ECR, secrets, Kyverno, ArgoCD
```
Tạo ~86 resource. Lấy output dùng cho bước sau:
```bash
terraform output     # executor_role_arn, ai_engine_role_arn, ecr_executor_url, audit_bucket_name, ...
```

## 3) Kubeconfig
```bash
aws eks update-kubeconfig --name cdo-eks-cluster-dev --region ap-southeast-1
kubectl get nodes      # phải Ready (2 node)
```

## 4) Build & push image executor lên ECR
```bash
ECR=012619468490.dkr.ecr.ap-southeast-1.amazonaws.com
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin $ECR
docker build --platform linux/amd64 -t $ECR/cdo-executor:v1 ./executor
docker push $ECR/cdo-executor:v1
```
> ECR là **IMMUTABLE** → mỗi lần build phải đổi tag (v1, v2, …). Image này dùng cho **cả executor lẫn mock-ai**.

## 5) Điền placeholder rồi apply `k8s/`
Các file `k8s/` để placeholder (điền từ `terraform output`):
| Placeholder | Giá trị |
|---|---|
| `REPLACE_WITH_EXECUTOR_ROLE_ARN` | `terraform output -raw executor_role_arn` |
| `REPLACE_WITH_ECR_URL:latest` | `<ECR>/cdo-executor:v1` |
| `REPLACE_WITH_AUDIT_BUCKET` | `terraform output -raw audit_bucket_name` |

```bash
kubectl apply -f k8s/00-namespaces.yaml
kubectl apply -f k8s/01-rbac.yaml          # SA tf3-cdo-controller + Role tenant-a/b (§3.D)
kubectl apply -f k8s/04-workloads.yaml     # podinfo tenant-a/b (workload mẫu)
kubectl apply -f manifests/kyverno/policies/         # 3 ClusterPolicy (replicas 1..10, memory<=4Gi, ns allowlist)
kubectl apply -f manifests/networkpolicies/          # ingress/egress ai-engine
kubectl apply -f k8s/02-mock-ai.yaml       # mock AI (tới khi AI team giao image thật)
kubectl apply -f k8s/03-executor.yaml      # executor
```

## 6) Verify
```bash
kubectl get pods -n kyverno -n argocd                       # Running
kubectl get pods -n self-heal-system -n tenant-a -n tenant-b
```

---

## 7) Demo self-heal (production `--watch`)
```bash
# chạy executor ở chế độ giám sát + cooldown
kubectl set env deploy/cdo-executor -n self-heal-system CDO_POLL_INTERVAL_S=15 CDO_VERIFY_MAX_WAIT_S=5
kubectl patch deploy/cdo-executor -n self-heal-system --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/command","value":["python","main.py","--watch"]}]'

# gây lỗi OOM thật trên workload tenant-a
kubectl set resources deploy/cdo-sample-api -n tenant-a -c podinfo --limits=memory=8Mi --requests=memory=8Mi

# xem executor tự phát hiện -> PATCH_MEMORY_LIMIT -> auto_resolved
kubectl logs deploy/cdo-executor -n self-heal-system -f
kubectl get deploy cdo-sample-api -n tenant-a -o jsonpath='{..limits.memory}'   # tự nâng lên 1Gi
```
Kết quả mong đợi (log): `[watcher] phát hiện OOM_KILL → action_plan PATCH_MEMORY_LIMIT → safety_passed → execute_done → incident_closed auto_resolved`. Audit ghi vào S3 (`audit/<tenant>/<correlation_id>.json`), idempotency key vào DynamoDB.

---

## 8) Teardown (cắt tiền)
```bash
cd infra/envs/dev
terraform destroy
```
> ⚠️ **Audit S3 dùng Object Lock GOVERNANCE 90 ngày** + `force_destroy=false` → destroy có thể **báo lỗi ở bucket audit** (object còn bị khoá). Phần đắt (EKS/NAT/node) vẫn được xoá. Muốn xoá nốt bucket: dùng `s3:BypassGovernanceRetention` xoá các version rồi `terraform destroy` lại — **lưu ý mất audit evidence**.

---

## Troubleshooting (các lỗi đã gặp & cách xử)
1. **Helm: `no cached repo found ... prometheus-community-index.yaml`** → terraform-provider-helm cần repo cache local. Cài `helm` + `helm repo add argo|kyverno` + `helm repo update`. Cache mặc định ở `%TEMP%/helm/repository` (set `HELM_REPOSITORY_CACHE`/`HELM_REPOSITORY_CONFIG` nếu lệch).
2. **ECR `docker login` 400 (PowerShell)** → pipe `get-login-password` hỏng; dùng biến: `$pw=(aws ecr get-login-password...); docker login --password $pw`.
3. **`init`/apply lỗi 301 region / sai bucket** → backend phải là `...-ap-southeast-1-dev` region `ap-southeast-1` (main cũ ghi us-east-1 — đã sửa trên nhánh này).
4. **EKS API `i/o timeout` từ laptop** → endpoint phải bật public (`cluster_endpoint_public_access=true` — đã set). Production nên giới hạn `public_access_cidrs`.
5. **executor pod crash `Invalid kube-config / No configuration found`** → đã fix: `k8s_client` auto-detect in-cluster (SA token) vs kubeconfig.
6. **executor `ai_unavailable` liên tục** → mock-ai phải bind `0.0.0.0` (không `127.0.0.1`) để reachable qua Service — đã fix.
7. **`kubectl logs` rỗng dù đang chạy** → Python buffer stdout; đã set `ENV PYTHONUNBUFFERED=1` trong Dockerfile.
8. **Re-run scenario bị `idempotency_duplicate_denied`** → đúng (idempotency key deterministic theo `correlation_id`, DynamoDB nhớ 24h). Xoá item DDB nếu muốn replay.
9. **`CreateRole/CreateLogGroup ... already exists`** → orphan từ apply-fail trước; `terraform import` vào state (hoặc xoá thủ công) rồi apply lại.

## Known issues / nên cải tiến
- `k8s/03-executor.yaml` chạy `run_scenarios.py` dưới dạng **Deployment** = anti-pattern (loop + patch lặp). Nên chuyển sang **Job** (test) hoặc `--watch` (production).
- `k8s/` còn placeholder → cân nhắc kustomize/envsubst để render tự động.
- mock-ai chỉ tạm; thay bằng image AI thật (`manifests/ai-engine/deployment.yaml.template`) khi AI team bàn giao.
