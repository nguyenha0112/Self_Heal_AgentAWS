# Requirements Analysis - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Draft cho W11 Pack #1  
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

## 6. Target Patterns (cần bàn với AI)

### 6.1 Patterns build thật

CDO-02 đề xuất 3 patterns build thật:

| Pattern | Action CDO dự kiến | Lý do chọn |
|---|---|---|
| `service_stuck` | Rollout restart deployment | Dễ demo, sát với đề bài, action rõ ràng |
| `OOMKilled` / `high_restart_count` | Restart hoặc escalate với context bundle | Có Kubernetes event/metric rõ |
| `queue_backlog` | Scale worker trong max limit | Thể hiện orchestration và blast-radius |

### 6.2 Patterns design-only

CDO-02 đề xuất 2 patterns design-only:

| Pattern | Action thiết kế | Lý do design-only |
|---|---|---|
| `bad_deployment_rollout` | Rollback rollout revision | Cần rollout history và setup kỹ hơn |
| `node_pressure` | Cordon/drain hoặc reschedule | Risk cao, không nên execute thật trong scope demo sớm |

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
| Observability | Logs + metrics + K8s events first; traces optional | Đủ để support 3 known patterns đầu |
| Cost control | W11 draft estimate, W12 refine with evidence | Tránh over-architecting |

## 8. AI-CDO Contract Dependencies (cần bàn với AI)

CDO-02 cần AI team cung cấp và ký 3 contracts:

1. **Telemetry Contract**: AI cần logs/metrics/events nào từ CDO cho từng pattern.
2. **AI API Contract**: CDO gọi endpoint nào, request schema là gì, response schema là gì.
3. **Deployment Contract**: AI endpoint deploy ở đâu, auth/timeout/retry/fallback như thế nào.

CDO-02 yêu cầu contract phải làm rõ:

- Endpoints: `POST /v1/detect`, `POST /v1/decide`, `POST /v1/verify`.
- Required request fields: `correlation_id`, `idempotency_key`, `tenant_id`, `namespace`, `dry_run_mode`, `alert`, `context`.
- `/v1/decide` response phải có: `decision`, `pattern`, `confidence`, `action_plan`, `target`, `blast_radius`, `rollback_plan`, `verify_plan`.
- AI không giữ kubeconfig và không gọi Kubernetes trực tiếp.
- Nếu AI timeout/503: CDO không execute, chỉ escalate và audit.

## 9. Assumptions

- Team chính thức là **CDO-02**.
- CDO-02 đã chốt angle **K8s-heavy / Kubernetes Workflow Orchestration**.
- Sandbox chạy trên AWS/EKS.
- Region mặc định theo client brief là `us-east-1`, trừ khi trainer/mentor yêu cầu khác.
- Observability ưu tiên AWS-native: CloudWatch Logs, CloudWatch Metrics, Container Insights; Prometheus/OpenTelemetry/X-Ray là optional nếu kịp.
- Audit storage ưu tiên S3 Object Lock hoặc append-only storage tương đương.
- CDO-02 có thể dùng mock/skeleton AI endpoint từ T6 W11 đến trước integration session W12.

## 10. Open Questions (cần bàn với AI / trainer)

Các câu hỏi còn lại cần chốt với AI team hoặc trainer/mentor.

### 10.1 Cần chốt với AI team

1. AI có support 3 build patterns `service_stuck`, `OOMKilled/high_restart_count`, `queue_backlog` không?
2. AI có đồng ý 2 design-only patterns `bad_deployment_rollout`, `node_pressure` không?
3. AI đã confirm endpoint `/v1/detect`, `/v1/decide`, `/v1/verify` chưa?
4. Response của `/v1/decide` có đủ `decision`, `confidence`, `action_plan`, `target`, `rollback_plan`, `verify_plan` không?
5. AI cần telemetry cụ thể nào cho từng pattern: metrics, logs, Kubernetes events, traces có bắt buộc không?
6. AI skeleton endpoint khi nào có để CDO test integration?
7. Nếu AI timeout/503 thì AI có đồng ý rule: CDO không execute, chỉ escalate và audit không?

### 10.2 Cần chốt với trainer/mentor nếu chưa rõ

1. Trainer có bắt buộc S3 Object Lock cho audit không, hay append-only log được chấp nhận?
2. Trainer có yêu cầu region khác `us-east-1` không?
3. Trainer có yêu cầu base infra T6 phải chạy thật hoàn toàn không, hay skeleton + plan + commit evidence được chấp nhận nếu AWS setup chưa sẵn sàng?

## 11. Pack #1 Completion Checklist

- [ ] CDO angle locked.
- [ ] Build/design-only patterns confirmed with AI.
- [ ] AI contract open questions documented.
- [ ] NFR table reviewed by team.
- [ ] Assumptions confirmed or marked as risk.
- [ ] File committed as Pack #1 evidence.
