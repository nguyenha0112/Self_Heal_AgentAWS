# Deployment & CI/CD Design - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Status:** Draft for W11/W12 deployment design alignment  
**Last updated:** 2026-06-24  

## 1. Chiến lược IaC

### 1.1 Lựa chọn công cụ

CDO-02 chọn **Terraform** là công cụ IaC chính cho thiết kế triển khai của Self-Heal Engine. Lý do chính:

- Kiến trúc mục tiêu đang xoay quanh AWS và EKS, nên Terraform phù hợp để provision VPC, EKS, IAM, S3, DynamoDB và nền tảng observability.
- Terraform giúp tách rõ hạ tầng dùng chung và phần cấu hình theo môi trường.
- Terraform phù hợp với hướng skeleton/base infra đã mô tả trong `02_infra_design.md`.
- Terraform cũng khớp với các quyết định hiện có về `S3 Object Lock`, `DynamoDB conditional write` và observability stack.

State backend dự kiến:

- **Remote state:** S3
- **State lock:** S3 lockfile (`use_lockfile = true`)
- **State separation:** 1 state chính cho environment `sandbox`

CDO-02 không chọn CloudFormation hay CDK làm hướng chính trong capstone vì mục tiêu hiện tại là có một cấu trúc triển khai để review, để chia module, để plan/apply theo environment và để giảm coupling với code runtime.

Với scope hiện tại chỉ có **1 environment sandbox**, cách làm gọn nhất là:

- 1 S3 bucket cho remote state
- 1 state file cho `sandbox`
- 1 S3 lock file đi kèm state object

Hướng này đủ cho scope nhóm hiện tại, đồng thời ít moving parts hơn so với việc thêm DynamoDB chỉ để lock state.

### 1.2 Cấu trúc module

Cấu trúc IaC đề xuất cho CDO-02:

```text
infra/
  modules/
    vpc/                 # VPC, subnets, route tables, security groups
    eks/                 # EKS cluster, node groups, cluster access baseline
    iam/                 # IRSA, deployment roles, least-privilege policies
    observability/       # Prometheus stack, Grafana, CloudWatch integration
    audit/               # S3 audit bucket, Object Lock, retention controls
    idempotency/         # DynamoDB table cho idempotency lock
    tenant-bootstrap/    # namespace, RBAC, labels, sample workload baseline
  environments/
    sandbox/
  README.md
```

Ý nghĩa của cấu trúc này:

- `modules/` giữ logic dùng chung.
- `environments/` giữ biến và wiring cho `sandbox`.
- `tenant-bootstrap/` phục vụ yêu cầu multi-tenant Kubernetes tối thiểu với `tenant-a`, `tenant-b` và `platform`.

Trong scope capstone, **sandbox** là môi trường duy nhất cần implement. Không cần mở rộng sang `staging` hoặc `prod` trong bản hiện tại nếu nhóm chưa có nhu cầu thật.

### 1.3 Quản lý state

CDO-02 dùng chiến lược quản lý state như sau:

- Remote state trên S3 cho `sandbox`.
- S3 lockfile để tránh race condition khi có nhiều người chạy deploy.
- `terraform plan` là gate bắt buộc trên pull request.
- `terraform apply` chỉ được chạy sau khi đã review và merge.

Lợi ích của cách này:

- Giảm rủi ro ghi đè state.
- Tạo audit trail rõ hơn cho thay đổi hạ tầng.
- Phù hợp với deployment process có approval gate.
- Đơn giản hơn cho team vì không cần thêm DynamoDB table chỉ để lock state.

## 2. CI/CD pipeline

### 2.1 Các stage trong pipeline

CDO-02 đề xuất **GitHub Actions** làm công cụ CI/CD chính. Pipeline cần bao phủ cả:

- IaC
- Kubernetes manifests/Helm values
- Runtime components của executor, collector, webhook/mock integration nếu có

Luồng tổng quát:

```text
PR opened -> Lint -> Test -> Scan -> Terraform Validate/Plan -> Review -> Merge -> Apply/Sync -> Smoke Test
```

Bảng stage đề xuất:

| Stage | Tool | What it does | Quality gate |
|---|---|---|---|
| Lint | GitHub Actions + markdownlint/yamllint/terraform fmt check | Kiểm tra format docs, YAML, Terraform | No formatting error |
| Test | GitHub Actions + unit/integration test command của repo | Chạy test cho runtime components nếu có | Test pass |
| Scan | Gitleaks + Trivy + Checkov/tfsec | Secret scan, image scan, IaC security scan | No exposed secret, no CRITICAL issue |
| Validate | Terraform validate | Kiểm tra cú pháp và wiring IaC | Validate pass |
| Plan | Terraform plan | Preview thay đổi hạ tầng theo environment | Plan reviewed |
| Review | PR approval | Kiểm tra kỹ thuật và security | Approval required |
| Apply | Terraform apply + GitOps sync | Provision infra và sync in-cluster resources | Apply/sync success |
| Smoke | Custom scripts / kubectl / health checks | Kiểm tra sau deploy | All critical checks pass |

### 2.2 Chiến lược branch

Branch strategy đề xuất:

- `main` = production-ready hoặc final reviewed branch
- `develop` = integration branch cho team
- `feature/*` = branch cho từng hạng mục

Nguyên tắc merge:

- Mọi thay đổi deployable phải đi qua pull request.
- Merge vào `develop` dùng cho integration và test.
- Merge vào `main` cần review và approval rõ ràng.
- Không apply thay đổi hạ tầng từ branch cá nhân bỏ qua review gate.

### 2.3 Smoke test sau deploy

Smoke test là phần bắt buộc vì Self-Heal Engine không chỉ cần deploy xong, mà còn phải sẵn sàng cho detect/decide/verify flow. Các kiểm tra tối thiểu:

- EKS cluster và 3 namespace `platform`, `tenant-a`, `tenant-b` tồn tại đúng.
- RBAC deny được cross-tenant access ngoài scope.
- Prometheus, Alertmanager và Grafana đã Ready.
- CloudWatch audit log path hoạt động.
- Executor hoặc webhook receiver trả health check thành công.
- Nếu AI endpoint sẵn sàng, đường gọi private endpoint và auth flow phải được verify.

## 3. GitOps

### 3.1 Công cụ

CDO-02 đề xuất **ArgoCD** là công cụ GitOps ưu tiên cho tài nguyên trong cluster. Lý do:

- Phù hợp với workload Kubernetes-centric.
- Giúp tách rõ boundary:
- **Terraform** provision AWS base infra
- **ArgoCD** sync Kubernetes manifests và Helm releases
- Có khả năng quan sát drift và rollback theo Git revision.

Trong capstone, nếu chưa có đủ thời gian để dựng ArgoCD đầy đủ, phần này vẫn nên được viết là **target deployment model** vì nó khớp nhất với angle K8s-heavy của CDO-02.

### 3.2 Cấu trúc repo / sync

Hướng chia deployment responsibility:

- Terraform:
  - VPC
  - EKS
  - IAM/IRSA
  - S3 audit bucket
- ArgoCD:
  - Namespaces
  - RBAC
  - kube-prometheus-stack
  - executor/collector manifests
  - sample workloads cho tenant demo

### 3.3 Sync waves

Thứ tự sync đề xuất:

| Wave | Components |
|---|---|
| 0 | Namespace `platform`, `tenant-a`, `tenant-b`; baseline labels/annotations |
| 1 | RBAC, ServiceAccounts, IRSA bindings, configmaps |
| 2 | Observability stack: Prometheus, Alertmanager, Grafana |
| 3 | CDO executor, telemetry collector, webhook/mock integration |
| 4 | Tenant sample workloads và test scenarios |

### 3.4 Drift detection

CDO-02 ưu tiên có drift detection cho phần Kubernetes manifests:

- ArgoCD phát hiện sai khác giữa Git và cluster.
- Drift được review trước khi chấp nhận destructive sync.
- Các thay đổi nhạy cảm như RBAC, namespace, observability routing cần có approval thay vì auto-heal mù quáng.

## 4. Chiến lược triển khai

### 4.1 Strategy

Trong scope capstone, CDO-02 chọn **rolling update** là deployment strategy chính cho workload trong cluster. Đây là lựa chọn thực tế nhất vì:

- Đơn giản để chứng minh trong sandbox.
- Khớp với EKS/Kubernetes deployment model.
- Giảm rủi ro over-design khi repo chưa có bằng chứng cho traffic split canary.

**Canary deployment** được xem là hướng nâng cấp future-state, có thể áp dụng sau này nếu bổ sung Argo Rollouts hoặc có cơ chế traffic management rõ ràng.

### 4.2 Tiêu chí abort

Một deployment được xem là không an toàn nếu có các dấu hiệu sau:

- Error rate tăng bất thường sau deploy.
- Latency p95/p99 vượt ngưỡng đã đặt cho scenario.
- Pod không Ready trong cửa sổ startup hợp lý.
- Verify step thất bại hoặc phát hiện regression.
- Alert firing mới xuất hiện ngay sau deploy đối với thành phần vừa thay đổi.

Với Self-Heal Engine, observability không chỉ là monitoring, mà còn là deployment gate và rollback signal.

### 4.3 Cách rollback

CDO-02 cần tách rõ hai loại rollback:

**Rollback deployment pipeline**

- Kubernetes workload rollback về manifest/Git revision trước.
- Helm release rollback hoặc `kubectl rollout undo` nếu phù hợp.
- ArgoCD có thể sync lại revision an toàn trước đó.

**Rollback self-heal runtime action**

- Tương ứng với `rollback_plan` đi kèm trong `action_plan` AI trả về.
- Ví dụ: rollout undo sau restart/patch nếu verify fail.
- Nếu rollback không an toàn hoặc không đủ điều kiện, hệ thống phải escalate thay vì thử mutate thêm.

**Rollback infrastructure**

- Terraform không rollback tự động theo kiểu transaction.
- Cách an toàn là review thay đổi, sửa code về trạng thái hợp lệ, plan lại, rồi apply.

Mục tiêu của deployment design là fail-safe: khi không chắc chắn, ưu tiên dừng lại, rollback hoặc escalate thay vì tiếp tục deploy/mutate.

## 5. Tách biệt môi trường

Trong scope hiện tại, CDO-02 chỉ thiết kế và triển khai **1 environment sandbox**.

| Env | Purpose | Expected use |
|---|---|---|
| Sandbox | Dev, demo, scenario simulation, evidencing | Môi trường duy nhất trong capstone hiện tại |

Trong sandbox, separation được thể hiện bằng:

- Namespace `platform` cho executor, collector và thành phần dùng chung
- Namespace `tenant-a` cho workload tenant 1
- Namespace `tenant-b` cho workload tenant 2

Nguyên tắc tách biệt:

- 1 remote state cho sandbox.
- Secrets, RBAC và workload được tách theo namespace.
- Mỗi incident phải map rõ `tenant_id` về namespace tương ứng.
- Không cho phép action cross-tenant trong `tenant-a` và `tenant-b`.

Nếu về sau nhóm mở rộng thêm `staging` hoặc `prod`, cấu trúc `modules/` vẫn có thể tái sử dụng, nhưng bản hiện tại không cần over-design cho những môi trường đó.

## 6. Secrets trong pipeline

Security design của CDO-02 yêu cầu pipeline không được đưa secret vào Git hoặc CI logs. Deployment design đề xuất:

- CI dùng **OIDC + IAM assume-role** để lấy quyền tạm thời.
- Không dùng static AWS access keys trong GitHub Actions.
- Secret runtime được giữ trong AWS Secrets Manager hoặc Kubernetes Secret theo boundary cho phép.
- Pod trên EKS ưu tiên dùng IRSA thay vì inject AWS key.
- Secret scan trên pull request bằng Gitleaks hoặc công cụ tương đương.
- Pipeline phải redact token, auth header, kube token và thông tin nhạy cảm khỏi logs.

Nếu secret bị phát hiện trong PR:

- Block merge.
- Yêu cầu rotate secret nếu đó là secret thật.
- Ghi nhận đây là security incident nhỏ, không xem như warning thông thường.

## 7. Tenant onboarding deployment

CDO-02 không đặt mục tiêu build full self-service tenant provisioning platform trong capstone. Tuy nhiên, deployment design vẫn cần mô tả cách bootstrap tenant để chứng minh multi-tenant isolation.

### 7.1 Scope capstone

Luồng onboarding tenant tối thiểu:

```text
1. Provision namespace tenant mới
2. Tạo Role/RoleBinding theo least privilege
3. Gán labels/annotations tenant_id, environment, service
4. Deploy sample workload cho tenant
5. Chạy smoke test isolation và alert flow
```

### 7.2 Deployment model đề xuất

Trong tài liệu này, CDO-02 chọn hướng:

- **Terraform module** cho baseline provisioning cần có ở tầng infra/platform
- **GitOps manifest sync** cho namespace-scoped resources và sample workloads

Mẫu luồng:

```text
tenant request
-> update environment config / tenant manifest
-> Terraform provision baseline dependencies nếu cần
-> ArgoCD sync namespace resources
-> deploy sample workload
-> smoke test isolation
-> tenant ready
```

Template gốc có gợi ý `Step Function -> Terraform module tenant-provision`. Với CDO-02, hướng đó có thể được xem là **future-state automation**, nhưng không nên khẳng định là design đã chốt nếu team chưa có bằng chứng và chưa cần đến mức độ tự động hóa đó.

Trong bản hiện tại, CDO-02 chỉ cần chứng minh onboarding cho **2 tenant trong Kubernetes**:

- `tenant-a`
- `tenant-b`

## 8. Observability stack

Observability stack phục vụ cả hai mục tiêu:

- Vận hành và debug hệ thống
- Làm bằng chứng cho deployment gate, smoke test, rollback và verify

Bảng stack đề xuất:

| Component | Tool |
|---|---|
| Metrics | Prometheus + kube-state-metrics + node-exporter |
| Alerts | Alertmanager |
| Logs | CloudWatch Logs |
| Dashboards | Grafana |
| Traces | OpenTelemetry -> AWS X-Ray hoặc Jaeger |
| Audit trail | S3 Object Lock + CloudWatch Logs |

Vai trò của stack này trong deployment:

- Sau deploy, dashboard và alerts cho biết workload có ổn định không.
- Audit logs ghi lại ai deploy, deploy gì, rollout kết quả thế nào.
- Trace/log/metric giúp phân biệt lỗi do code, do config, hay do hạ tầng.
- Các metric như latency, error rate, memory pressure được tái sử dụng cho verify step của Self-Heal flow.

CDO-02 ưu tiên hướng quan sát sau:

```text
EKS workloads
-> Prometheus / CloudWatch / OpenTelemetry
-> Alerting + dashboards + audit logs
-> deployment gate / smoke test / verify signal
```

## 9. Open questions

Những điểm dưới đây cần tiếp tục chốt với AI team hoặc trainer trước khi chuyển từ design sang implementation đầy đủ:

- Traces có bắt buộc phải hoạt động đầy đủ trong demo, hay logs + metrics là đủ?
- Tenant onboarding có cần tự động hóa sâu hơn bằng workflow engine, hay Terraform + GitOps là đủ cho scope hiện tại?
- AI team có cung cấp environment/stub ổn định để smoke test private endpoint và auth flow không?

## Related documents

- `01_requirements_analysis.md` - Xác định scope, NFR và assumptions của CDO-02
- `02_infra_design.md` - Kiến trúc tổng thể, component model và workflow
- `03_security_design.md` - IAM, RBAC, secrets, audit và fail-safe controls
- `08_adrs.md` - Các quyết định kiến trúc đã được chấp nhận
