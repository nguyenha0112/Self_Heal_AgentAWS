# Requirements Analysis - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Ready for W11 Pack #1 review  
**Cập nhật lần cuối:** 2026-06-23  

## 1. Bối cảnh đề tài

Task Force 3 xây dựng **Self-Heal Engine** cho một nền tảng SaaS B2B đang vận hành hơn 200 microservices trên Kubernetes/EKS. Client là VP Engineering, đang gặp vấn đề on-call quá tải vì mỗi đêm có 2-4 page, trong đó khoảng 80% là các known patterns lặp lại như Pod OOMKilled, service stuck, queue backlog, cert expiring.

Client muốn xây một hệ thống tự động hóa xử lý sự cố theo pipeline:

```text
detect -> match runbook -> execute audited action -> verify -> escalate nếu fail
```

CDO-02 không xây AI model. Vai trò của CDO-02 là xây platform/infra để Self-Heal Engine chạy an toàn trên Kubernetes sandbox: nhận alert, gom context, gọi AI endpoint, kiểm tra safety gate, dry-run, execute action, verify kết quả, rollback/escalate nếu fail và ghi audit log.

## 2. Problem Statement

On-call engineers hiện đang mất nhiều thời gian cho các thao tác lặp lại, đặc biệt là những action có runbook rõ như restart deployment, scale worker hoặc xử lý OOMKilled. Nếu tự động hóa không có kiểm soát, hệ thống có thể gây unsafe action trên Kubernetes như thao tác sai namespace, scale quá mức, rollback sai target hoặc thiếu audit trail.

Vì vậy, yêu cầu của CDO-02 không chỉ là "gọi AI rồi execute", mà là xây một platform có guardrails rõ ràng:

- AI chỉ đưa ra decision/action plan.
- CDO enforce safety gate trước khi execute.
- Mọi action phải có dry-run, blast-radius, rollback plan, verify plan và audit.
- Multi-tenant isolation phải rõ ràng giữa ít nhất 2 tenants.
- Nếu AI timeout, confidence thấp hoặc action không an toàn thì CDO không execute, mà escalate và ghi audit.

## 3. Phạm vi CDO-02 phụ trách

CDO-02 sẽ phụ trách các phần sau:

| Hạng mục | Trách nhiệm của CDO-02 |
|---|---|
| Platform architecture | Thiết kế workflow alert -> AI -> safety -> execute -> verify -> audit |
| Kubernetes sandbox | EKS/Kubernetes cluster, namespaces, sample workloads |
| Multi-tenant isolation | Ít nhất `tenant-a` và `tenant-b`, tách namespace và RBAC |
| Safety gate | Validate tenant, namespace, confidence, blast-radius, rollback, verify |
| Execution layer | Executor/operator-style workflow để restart/scale/rollback theo action plan |
| Audit | Ghi audit log theo `correlation_id`, retention target >= 90 ngày |
| Observability | Logs, metrics, Kubernetes events; ưu tiên CloudWatch/Container Insights |
| Deployment/IaC | Terraform skeleton cho VPC, EKS, observability |
| AI integration | Consume 3 AI contracts, gọi AI endpoint theo schema đã ký |

## 4. Out Of Scope

CDO-02 không làm các phần sau trong scope capstone:

- Không build AI model hoặc decision engine.
- Không cho AI gọi Kubernetes trực tiếp.
- Không làm production traffic; chỉ sandbox + synthetic workload.
- Không làm multi-cluster federation.
- Không auto-discover pattern mới; chỉ implement/design known patterns.
- Không làm real PagerDuty/OpsGenie; Slack/mock pager là đủ.
- Không làm hash-chain crypto audit; S3 Object Lock hoặc append-only audit là đủ.
- Không làm cross-region replication.
- Không làm mTLS; bearer token/JWT là đủ cho capstone.

## 5. Differentiation Angle

- **Angle chọn:** K8s-heavy / Kubernetes Workflow Orchestration.
- **Why this angle:** TF3 là bài toán self-healing cho microservices chạy trên Kubernetes/EKS, nên CDO-02 chọn Kubernetes-native workflow để thao tác trực tiếp với workload, enforce RBAC theo namespace, kiểm soát blast-radius, dry-run, rollback, verify và audit. Trục tối ưu chính là **reliability** và **operational control**.
- **Trade-off chấp nhận:** Chi phí và độ phức tạp vận hành cao hơn serverless-first, nhưng đổi lại sát đề bài hơn, dễ chứng minh tenant isolation/RBAC hơn và phù hợp với self-heal trên Kubernetes workload.
- **Locked T3 W11:** 2026-06-23.

## 6. Target Patterns / Dataset Scope (cần bàn với AI)

Theo contract hiện tại của AI, phạm vi dữ liệu được căn theo **RE2/RE3 dataset** và hệ thống mẫu **Online Boutique**. Vì vậy CDO-02 cần align pattern demo với các signals/actions mà AI contract đã định nghĩa, thay vì tự đặt pattern theo tên quá chung chung.

### 6.1 Patterns build thật

CDO-02 đề xuất 3 patterns build thật:

| Pattern | Action CDO dự kiến | Lý do chọn |
|---|---|---|
| Service stuck / latency spike | `RESTART_DEPLOYMENT` | Khớp telemetry `istio_request_latency_p95` và action trong AI API Contract |
| Error rate spike / code-level fault | `RESTART_DEPLOYMENT` hoặc escalate với context bundle | Khớp `istio_request_error_rate`, `app_log_error_event`, `trace_span_error_event` |
| Memory pressure / OOM prevention | `ADJUST_MEMORY_LIMIT` hoặc escalate nếu không đủ an toàn | Khớp telemetry `container_memory_working_set_bytes` |

### 6.2 Patterns design-only

CDO-02 đề xuất 2 patterns design-only:

| Pattern | Action thiết kế | Lý do design-only |
|---|---|---|
| Queue/backpressure | `SCALE_UP_PODS` | Action có trong AI contract, nhưng cần dữ liệu queue rõ hơn |
| Secret/cert/config issue | `UPDATE_ENV_SECRET` | Action có trong AI contract, nhưng rủi ro cao hơn nên để design-only nếu chưa đủ guardrail |

Danh sách pattern cuối cùng cần được confirm với AI team trước khi ký contract.

## 7. Infra Non-Functional Requirements

| NFR | Target | Justification |
|---|---|---|
| Multi-tenant isolation | >= 2 tenants trong sandbox | Hard requirement của TF3 |
| Auto-resolve rate | >= 60% trên >= 10 scenarios | Hard requirement của TF3 |
| Scenario simulation | >= 4h test window | Hard requirement của TF3 |
| Unsafe action | 0 unsafe action | Không delete prod namespace, không IAM modify |
| Audit retention | >= 90 ngày | SOC2/compliance requirement |
| Safety checkpoint | Dry-run, blast-radius, verify, rollback, circuit breaker | Hard requirement của TF3 |
| AI endpoint timeout handling | Timeout/503 -> no execute, escalate + audit | Prevent unsafe automated action |
| Observability | Logs + metrics + traces theo AI contract | Cần đủ dữ liệu cho detect/decide/verify và trace end-to-end |
| Cost control | W11 draft estimate, W12 refine with evidence | Tránh over-architecting |

## 8. Clarifications Needed From Client/Trainer

Các điểm dưới đây cần hỏi trainer/mentor đóng vai client trước khi chốt final, vì nếu tự giả định sai thì có thể ảnh hưởng thiết kế W12.

| Chủ đề | Câu hỏi cần hỏi trainer/client | Ảnh hưởng nếu chưa chốt |
|---|---|---|
| Sandbox environment | T6/W12 có bắt buộc dùng EKS thật không, hay Kubernetes sandbox/local được chấp nhận nếu có evidence rõ? | Ảnh hưởng infra design và deployment plan |
| Region | Client/trainer có bắt buộc `us-east-1` theo brief không? | Ảnh hưởng Terraform variables, cost estimate, deployment |
| Audit storage | Audit có bắt buộc S3 Object Lock không, hay append-only log/DB được chấp nhận cho capstone? | Ảnh hưởng security design và cost |
| Auto-resolved definition | Một incident được tính auto-resolved khi action execute thành công hay khi metrics trở lại normal sau verify? | Ảnh hưởng test report và success criteria |
| Blast-radius limit | Một lần self-heal được thao tác tối đa bao nhiêu deployment/replica/namespace? | Ảnh hưởng safety gate |
| Escalation policy | Retry mấy lần trước khi escalate? Escalation message cần format Slack/Markdown/JSON? | Ảnh hưởng workflow và AI response |
| Observability requirement | Traces trong AI contract cần triển khai đầy đủ ở W12 hay chấp nhận phased implementation? | Ảnh hưởng tool choice: CloudWatch, Prometheus, X-Ray/OpenTelemetry |
| Offline simulation | Trainer có chấp nhận Mock Mode theo RE2/RE3 dataset cho action như restart/scale không? | Ảnh hưởng demo và test evidence |

Trong khi chờ trainer/client confirm, CDO-02 sẽ ghi các điểm này là **assumption**, không xem là quyết định cuối cùng.

## 9. AI-CDO Contract Dependencies (cần bàn với AI)

AI team đã publish 3 contracts tại repo `AIops-g4/Capstone-Phase-2-Code/tf-3/ai/contracts`. CDO-02 cập nhật requirement theo các điểm chính dưới đây.

Mục tiêu của CDO-02 trong Pack #1 là chứng minh platform design **consume được contract của AI**, không tự thiết kế lệch interface. Các phần telemetry, API integration, security và deployment của CDO-02 sẽ bám theo 3 contract này, trừ các điểm cần push-back/clarify ở mục 9.4.

### 9.1 Telemetry Contract

CDO-02 cần thu thập/chuẩn hóa và gửi các signals sau cho AI:

| Signal | CDO responsibility | Used for |
|---|---|---|
| `istio_request_error_rate` | Tính từ error/request counters, emit mỗi 5 giây | Detect và verify lỗi service |
| `istio_request_latency_p95` | Đọc latency p95 từ metrics source | Detect service stuck/latency spike |
| `container_memory_working_set_bytes` | Đọc memory usage theo container/pod | Detect memory pressure/OOM prevention |
| `app_log_error_event` | Parse logs ERROR/stack trace | Diagnose code-level fault |
| `trace_span_error_event` | Parse traces có lỗi span | Diagnose lỗi liên dịch vụ |

Yêu cầu chung từ AI contract:

- Mọi signal phải có `tenant_id`.
- Với offline dataset, CDO inject `tenant_id` là `tnt-re2-simulation` hoặc `tnt-re3-simulation`.
- Timestamp dùng RFC3339 UTC.
- CDO phải lọc/mã hóa PII trước khi gửi log sang AI.

CDO-02 sẽ đáp ứng bằng cách:

- Thiết kế telemetry pipeline ưu tiên CloudWatch/Container Insights/Prometheus-compatible metrics.
- Chuẩn hóa metrics/logs/traces thành JSON trước khi gọi AI API.
- Gắn `tenant_id`, `correlation_id` và timestamp UTC cho mọi request.
- Với W11 Pack #1, mô tả schema và nguồn dữ liệu; W12 mới thu evidence thật từ sandbox.
- Traces được giữ trong schema theo AI contract; mức triển khai thực tế sẽ được chốt trong W12 plan và phụ thuộc thời gian tích hợp OpenTelemetry/X-Ray.

### 9.2 AI API Contract

Endpoint AI cung cấp:

```text
POST /v1/detect
POST /v1/decide
POST /v1/verify
```

Authentication và headers:

```text
Authorization: IAM SigV4
X-Tenant-Id: cdo-2 / tnt-re2-simulation / tnt-re3-simulation
Idempotency-Key: UUID v4 cho request thay đổi trạng thái
X-Correlation-Id hoặc correlation_id để trace toàn bộ workflow
```

Luồng tích hợp:

```text
/v1/detect -> AI trả anomaly_detected, severity, anomaly_context, confidence, correlation_id
/v1/decide -> AI trả matched_runbook, action_plan[], blast_radius_config
CDO execute/mock execute action
/v1/verify -> AI trả success, regression_detected, next_action, escalation_bundle nếu cần
```

Các action AI contract đang định nghĩa:

```text
RESTART_DEPLOYMENT
SCALE_UP_PODS
UPDATE_ENV_SECRET
ADJUST_MEMORY_LIMIT
```

SLA/API behavior từ contract:

- `/v1/detect` p99 < 300ms.
- `/v1/decide` p99 < 500ms.
- `/v1/verify` p99 < 500ms.
- Availability target 99.9%.
- Rate limit 120 requests/minute/tenant.
- `400`: không retry tự động.
- `409`: trùng `Idempotency-Key`.
- `429`: exponential backoff.
- `503`: CDO phải fallback bằng static runbook hoặc escalation.

CDO-02 sẽ đáp ứng bằng cách:

- Xây executor/safety gate consume `action_plan[]` từ `/v1/decide`.
- Chỉ execute các action nằm trong allow-list của contract: `RESTART_DEPLOYMENT`, `SCALE_UP_PODS`, `UPDATE_ENV_SECRET`, `ADJUST_MEMORY_LIMIT`.
- Validate `tenant_id`, target namespace, blast-radius, rollback plan và verify plan trước khi execute.
- Dùng `Idempotency-Key` để tránh execute trùng một incident.
- Với `429`, dùng retry/backoff theo contract.
- Với `503`, mặc định không tự ý execute; CDO sẽ escalate + audit, trừ khi static runbook fallback đã được AI/CDO thống nhất.

### 9.3 Deployment Contract

Theo contract AI:

- AI Engine chạy dạng shared backend service trên **ECS Fargate**.
- Endpoint nội bộ: `https://ai-engine.tf-3.internal/`.
- Auth: IAM SigV4.
- Tenant ID cho CDO-02: `cdo-2`.
- AI service chạy private subnet, internal ALB, port `8080`.
- Health endpoints: `GET /health`, `GET /ready`, `GET /metrics`.
- Logs: CloudWatch Logs.
- Metrics: Prometheus endpoint.
- Traces: OpenTelemetry -> Jaeger hoặc AWS X-Ray.
- Audit: S3 Object Lock Compliance Mode, retention tối thiểu 90 ngày.

CDO-02 sẽ đáp ứng bằng cách:

- Thiết kế network path để CDO executor gọi AI endpoint nội bộ theo deployment contract.
- Sử dụng IAM SigV4 theo yêu cầu auth của AI.
- Gắn tenant ID `cdo-2` cho requests của CDO-02.
- Ghi log request/response theo `correlation_id` để trace được end-to-end.
- Thiết kế audit storage tương thích S3 Object Lock 90 ngày.
- Tách rõ AI endpoint là decision service; CDO executor là nơi enforce safety và execute action, trừ khi AI/CDO thống nhất lại boundary khác.

### 9.4 Điểm CDO cần push-back / clarify với AI

Deployment contract hiện có một điểm cần làm rõ: tài liệu AI nhắc tới việc AI Task Role có thể fetch kubeconfig và gọi EKS API để execute self-heal actions. Điều này có thể mâu thuẫn với angle CDO-02 đã chọn: **AI chỉ decide, CDO executor mới mutate Kubernetes**.

CDO-02 cần chốt lại với AI:

- AI có thật sự cần kubeconfig không?
- AI có execute action trực tiếp không, hay chỉ trả `action_plan` cho CDO?
- Nếu AI giữ kubeconfig, boundary RBAC cụ thể ra sao?
- Nếu CDO là executor duy nhất, cần sửa Deployment Contract để bỏ quyền AI gọi EKS API.
- Offline Simulation Mode nghĩa là CDO chỉ mock execute action, vậy evidence W12 sẽ là mock action hay action thật trên sandbox?

## 10. Assumptions

- Team chính thức là **CDO-02**.
- CDO-02 đã chốt angle **K8s-heavy / Kubernetes Workflow Orchestration**.
- Sandbox target là AWS/EKS, nhưng mức bắt buộc chạy thật ở T6 cần trainer xác nhận.
- Region mặc định theo client brief là `us-east-1`, trừ khi trainer/mentor yêu cầu khác.
- Observability theo contract AI gồm CloudWatch Logs, Prometheus metrics endpoint và OpenTelemetry traces về Jaeger hoặc AWS X-Ray.
- Audit storage theo contract AI là S3 Object Lock Compliance Mode, retention tối thiểu 90 ngày.
- CDO-02 có thể dùng mock/skeleton AI endpoint từ T6 W11 đến trước integration session W12.

## 11. Open Questions (cần bàn với AI / trainer)

Các câu hỏi còn lại cần chốt với AI team hoặc trainer/mentor.

### 11.1 Cần chốt với AI team

1. AI có confirm 3 build patterns: service stuck/latency spike, error rate spike/code-level fault, memory pressure/OOM prevention không?
2. AI có đồng ý 2 design-only patterns: queue/backpressure và secret/cert/config issue không?
3. CDO-02 có cần đổi naming pattern để khớp RE2/RE3 và Online Boutique không?
4. AI có thật sự cần kubeconfig/EKS API permission không, hay chỉ trả `action_plan`?
5. Offline Simulation Mode sẽ mock action hoàn toàn hay vẫn cần CDO thao tác Kubernetes sandbox?
6. AI skeleton endpoint khi nào có để CDO test integration?
7. Với `503`, CDO nên ưu tiên static runbook fallback hay escalation thẳng cho SRE?

### 11.2 Cần chốt với trainer/mentor nếu chưa rõ

1. Trainer có bắt buộc S3 Object Lock cho audit không, hay append-only log được chấp nhận?
2. Trainer có yêu cầu region khác `us-east-1` không?
3. Trainer có yêu cầu base infra T6 phải chạy thật hoàn toàn không, hay skeleton + plan + commit evidence được chấp nhận nếu AWS setup chưa sẵn sàng?

## 12. Pack #1 Completion Checklist

- [ ] CDO angle locked.
- [ ] Build/design-only patterns confirmed with AI.
- [ ] AI contract open questions documented.
- [ ] NFR table reviewed by team.
- [ ] Assumptions confirmed or marked as risk.
- [ ] File committed as Pack #1 evidence.
