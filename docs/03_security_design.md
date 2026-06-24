# Security Design - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Ready for W11 Pack #1 review  
**Cập nhật lần cuối:** 2026-06-23  

## 1. Security Goals

Mục tiêu bảo mật của CDO-02 là cho phép self-heal tự động nhưng không gây unsafe action trên Kubernetes. AI có thể đề xuất action, nhưng mọi thao tác mutate workload phải đi qua CDO safety gate, RBAC, dry-run, rollback/verify và audit.

Security goals chính:

- Zero unsafe action trong sandbox.
- Multi-tenant isolation giữa ít nhất 2 tenants.
- Least privilege cho Kubernetes RBAC và AWS IAM.
- Audit log tamper-evident, retention tối thiểu 90 ngày.
- Không để secret/kubeconfig lộ trong repo, log hoặc container image.
- Ghi đủ evidence để trace một incident theo `correlation_id`.

## 2. Đọc nhanh: security của CDO-02 bảo vệ cái gì?

Self-heal là hệ thống tự động sửa lỗi. Điểm rủi ro là nếu tự động sai, nó có thể làm hỏng workload khác. Vì vậy security design của CDO-02 tập trung vào 4 câu hỏi:

```text
1. Ai được quyền gọi AI?
2. Ai được quyền thao tác Kubernetes?
3. Làm sao chặn action sai tenant/sai namespace?
4. Làm sao chứng minh sau này action nào đã xảy ra?
```

CDO-02 trả lời bằng 4 lớp bảo vệ:

| Lớp bảo vệ | Dùng để làm gì? |
|---|---|
| IAM/Auth | Bảo đảm chỉ service hợp lệ được gọi AI/AWS |
| Kubernetes RBAC | Giới hạn quyền executor trên Kubernetes |
| Safety Gate | Chặn action sai tenant, quá blast-radius hoặc thiếu rollback/verify |
| Audit Log | Ghi lại toàn bộ detect/decide/execute/verify để truy vết |

### 2.1 Ví dụ dễ hiểu

Nếu AI đề xuất:

```text
Restart deployment tenant-b/api-service
```

Nhưng incident thật thuộc:

```text
tenant-a
```

Thì CDO phải:

```text
1. Safety gate phát hiện sai tenant.
2. Không gọi Kubernetes API.
3. Ghi audit: denied_cross_tenant.
4. Escalate nếu cần.
```

Đây là lý do CDO-02 không để AI tự execute trực tiếp.

## 3. Network Security

### 3.1 Network Layout

```mermaid
graph TB
    subgraph "AWS VPC"
        subgraph "Private Subnets"
            EKS[EKS / Kubernetes Sandbox]
            EXEC[CDO Executor Pod]
            AI[AI Engine Internal ALB -> ECS Fargate]
        end

        subgraph "AWS Services"
            CW[CloudWatch Logs]
            S3[S3 Object Lock Audit]
            SM[Secrets Manager]
        end
    end

    EXEC -->|HTTPS + IAM SigV4| AI
    EXEC -->|Kubernetes API| EKS
    EXEC --> CW
    EXEC --> S3
    EXEC --> SM
```

### 3.2 Network Rules

- AI endpoint là internal endpoint, không public Internet.
- CDO executor gọi AI qua HTTPS và IAM SigV4.
- Kubernetes API access chỉ dành cho executor ServiceAccount/Role phù hợp.
- Audit/log traffic đi tới CloudWatch và S3.
- Nếu cần NAT/VPC endpoints, ưu tiên VPC endpoints cho S3, CloudWatch, Secrets Manager để giảm public exposure.

## 4. IAM And Authentication

IAM/Auth trả lời câu hỏi: service nào được gọi service nào. Với contract AI hiện tại, CDO executor gọi AI bằng IAM SigV4 và tenant ID `cdo-2`.

| Identity | Used by | Permissions |
|---|---|---|
| CDO executor AWS role | Executor pod/task | Gọi AI endpoint với IAM SigV4, ghi audit S3, ghi logs |
| CDO telemetry preprocessor role | Preprocessor/collector | Đọc telemetry source, ghi SQS telemetry queue nếu dùng Offline Simulation Mode |
| AI service role | AI ECS Fargate | Theo deployment contract của AI |
| Deploy role | Terraform/CI | Tạo VPC/EKS/IAM/S3/observability theo scope |
| Readonly reviewer role | Mentor/trainer review | Read-only logs, audit, infra describe |

CDO-02 cần làm rõ với AI một điểm quan trọng: deployment contract AI có nhắc AI có thể fetch kubeconfig/gọi EKS API. Nếu CDO-02 giữ boundary "AI only decide, CDO executor execute", thì AI role không nên có quyền mutate Kubernetes.

## 5. Kubernetes RBAC

RBAC là lớp giới hạn quyền trong Kubernetes. Mục tiêu là executor chỉ có quyền vừa đủ để làm demo self-heal, không có quyền nguy hiểm như delete namespace hoặc sửa cluster-wide resource.

CDO-02 dùng namespace-based RBAC:

| Namespace | Purpose |
|---|---|
| `platform` | Chạy CDO executor, telemetry collector |
| `tenant-a` | Workload tenant A |
| `tenant-b` | Workload tenant B |

RBAC principles:

- Executor không dùng `cluster-admin`.
- Role theo namespace chỉ cho phép verbs cần thiết.
- Mutating verbs chỉ cấp cho resource cần demo: `deployments`, `pods`, `replicasets` nếu cần.
- Không cấp quyền delete namespace, modify IAM, modify cluster-wide resource.
- Cross-namespace action phải bị deny bởi safety gate và RBAC.

Ví dụ quyền tối thiểu dự kiến:

```text
get/list/watch: pods, deployments, replicasets, events
patch/update: deployments scale/restart target
create: events hoặc configmap audit marker nếu cần
```

## 6. Tenant Isolation

Tenant isolation bảo đảm tenant này không bị action nhầm sang tenant khác. Đây là hard requirement của TF3.

Tenant isolation được enforce ở 3 lớp:

1. **Request layer:** mọi request có `X-Tenant-Id` hoặc `tenant_id`.
2. **Safety layer:** action target namespace phải khớp tenant.
3. **Kubernetes layer:** ServiceAccount/RoleBinding chỉ có quyền trong namespace được phép.

Nếu AI trả action target `tenant-b` cho incident của `tenant-a`, CDO executor phải:

```text
deny action -> không gọi Kubernetes API -> ghi audit denied_cross_tenant -> escalate nếu cần
```

## 7. Secrets Management

Secrets management bảo đảm token, signing key, kube access và AWS credential không bị lộ.

Secrets dự kiến:

| Secret | Storage | Accessed by |
|---|---|---|
| AI endpoint auth/IAM config | IAM/IRSA hoặc AWS SDK default chain | CDO executor |
| Webhook signing key | AWS Secrets Manager hoặc K8s Secret | Alert ingestor |
| Kube access | Kubernetes ServiceAccount token | CDO executor |
| Audit bucket config | Terraform variables/outputs | Executor/deploy pipeline |
| Idempotency lock table config | Terraform outputs / env var | CDO executor |

Controls:

- Không commit secret vào Git.
- Không log bearer token, SigV4 headers đầy đủ hoặc kube token.
- Redact PII và credential-like strings trong logs.
- Ưu tiên IRSA thay vì static AWS keys trong pod.
- Idempotency lock dùng DynamoDB conditional write hoặc Redis TTL theo deployment contract; CDO-02 ưu tiên DynamoDB để tránh static state trong pod.

## 8. Audit Logging

Audit là phần giúp trainer/client kiểm tra: incident nào xảy ra, AI đã quyết định gì, CDO có execute không, kết quả ra sao. Không có audit thì self-heal rất khó được tin tưởng.

Audit là hard requirement của TF3. CDO-02 thiết kế audit theo `correlation_id` để truy vết toàn bộ incident.

Mỗi incident cần ghi:

```text
alert_received
telemetry_collected
detect_called
detect_response_received
decide_called
action_plan_received
idempotency_lock_acquired / idempotency_duplicate_denied
safety_passed / safety_denied
dry_run_done
execute_done
verify_called
verify_done
rollback_done / escalated
```

Audit record tối thiểu:

| Field | Purpose |
|---|---|
| `timestamp` | Thời điểm event |
| `correlation_id` | Trace toàn incident |
| `tenant_id` | Tenant bị ảnh hưởng |
| `namespace` | Namespace target |
| `action_type` | Action AI đề xuất |
| `decision` | execute/deny/escalate |
| `result` | success/failure/denied |
| `reason` | Lý do safety deny hoặc failure |
| `idempotency_key` | Chống execute trùng action |

Storage target theo contract AI: **S3 Object Lock Compliance Mode**, retention tối thiểu 90 ngày.

## 9. Data Protection

- Logs gửi sang AI phải lọc/mã hóa PII nếu có.
- Telemetry payload chỉ nên chứa fields trong telemetry contract.
- Audit log lưu input/output hash nếu payload lớn hoặc nhạy cảm.
- Encryption at rest dùng S3 SSE-KMS nếu có thể.
- Encryption in transit dùng HTTPS/TLS.

## 10. Failure And Abuse Cases

Phần này liệt kê các tình huống nguy hiểm và control tương ứng. Mục tiêu chung là fail-safe: khi không chắc thì không execute.

| Case | Control |
|---|---|
| AI trả action ngoài allow-list | Safety gate deny |
| AI trả namespace sai tenant | Safety gate deny + RBAC deny |
| AI timeout/503 | No execute, escalate + audit |
| Idempotency key trùng | Không execute trùng |
| SQS telemetry message sai schema | Reject message, log validation error, không gọi AI |
| Audit write fail | Stop action hoặc mark incident unsafe |
| Executor bị lỗi giữa action | Verify/rollback/escalate theo trạng thái audit |
| Secret bị lộ trong log | Redaction + không log sensitive headers |

## 11. Open Questions

- AI có thật sự cần kubeconfig/EKS API permission không?
- Nếu AI giữ kubeconfig, boundary RBAC giữa AI và CDO executor là gì?
- Trainer có bắt buộc S3 Object Lock thật cho W11/T6 không, hay W12 mới cần evidence?
- Traces có bắt buộc phải triển khai đầy đủ trong W12 demo không?
- Offline Simulation Mode đã là Mock Mode theo AI contract; trainer có cần thêm bằng chứng action thật trên Kubernetes sandbox không?

## Related Documents

- `01_requirements_analysis.md`
- `02_infra_design.md`
- `08_adrs.md`
