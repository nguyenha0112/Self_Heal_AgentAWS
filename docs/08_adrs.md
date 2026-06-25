# Architecture Decision Records - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Ready for W11 Pack #1 review  
**Cập nhật lần cuối:** 2026-06-25 (sync AI commit 86b32e7)  

ADR là nơi ghi lại các quyết định kiến trúc quan trọng, lý do chọn và trade-off. File này append-only; nếu decision thay đổi ở W12 thì thêm ADR mới hoặc đánh dấu ADR cũ là superseded.

---

## ADR-001 - Chọn K8s-heavy / Kubernetes Workflow Orchestration

- **Status:** Accepted
- **Date:** 2026-06-23

### Context

TF3 là bài toán Self-Heal Engine cho hệ thống hơn 200 microservices chạy trên Kubernetes/EKS. Các action cần demo như restart deployment, scale worker, adjust memory limit, verify pod/metrics đều liên quan trực tiếp đến Kubernetes workload.

### Decision

CDO-02 chọn angle **K8s-heavy / Kubernetes Workflow Orchestration**. CDO executor sẽ chạy gần Kubernetes workload, nhận action plan từ AI, enforce safety gate và execute action qua Kubernetes API.

### Consequences

- Pro: Sát đề TF3 và dễ demo self-heal thật trên Kubernetes.
- Pro: Dễ chứng minh RBAC, namespace isolation, blast-radius và audit.
- Trade-off: Chi phí và độ phức tạp cao hơn serverless-first.
- Trade-off: Team cần kiểm soát tốt Kubernetes manifests, RBAC và observability.

### Alternatives considered

- Serverless-first: ít vận hành hơn nhưng không sát thao tác Kubernetes.
- Managed-services heavy: dùng nhiều AWS service hơn nhưng khó thể hiện operator/workflow control trong cluster.
- Event-driven hybrid: mạnh về retry/queue nhưng dễ over-engineer trong thời gian capstone.

---

## ADR-002 - AI là decision service, CDO executor là execution boundary

- **Status:** Accepted, pending AI contract clarification
- **Date:** 2026-06-23

### Context

AI contract định nghĩa `/v1/detect`, `/v1/decide`, `/v1/verify` và trả `action_plan[]`. Deployment contract mới đã chốt AI Engine không giữ kubeconfig và không gọi Kubernetes/EKS API trực tiếp. Điều này khớp boundary CDO-02 chọn: AI là decision service, CDO là execution control plane.

### Decision

CDO-02 chọn boundary: **AI chỉ decide, CDO executor mới execute**. AI trả action plan; CDO validate tenant, namespace, `allowed_namespaces`, blast-radius, local rollback/runbook path, `verify_policy` rồi mới execute hoặc deny/escalate.

Khi AI trả `pattern_type: "urgent"`, CDO executor gọi Kubernetes API trực tiếp sau safety gate (RTO target < 60s). Khi AI trả `pattern_type: "deferred"`, CDO tạo Git commit hoặc PR để GitOps (ArgoCD) sync về cluster, không direct mutate Kubernetes.

### Consequences

- Pro: Rõ ownership giữa AI và CDO.
- Pro: CDO kiểm soát được zero unsafe action.
- Pro: Audit log tập trung qua CDO executor.
- Trade-off: CDO phải build executor/safety gate đầy đủ.
- Trade-off: CDO phải chịu trách nhiệm đầy đủ cho RBAC, safety gate và audit khi execute.

### Alternatives considered

- AI trực tiếp gọi Kubernetes API: nhanh hơn cho AI demo nhưng rủi ro quyền hạn và audit boundary.
- Shared execution giữa AI và CDO: linh hoạt nhưng dễ mơ hồ ownership.

---

## ADR-003 - Chọn namespace-based tenant isolation và RBAC least privilege

- **Status:** Accepted
- **Date:** 2026-06-23

### Context

TF3 yêu cầu multi-tenant ít nhất 2 tenants với RBAC isolation và zero unsafe action. CDO cần chứng minh tenant A không bị action nhầm sang tenant B.

### Decision

CDO-02 dùng namespace-based isolation:

```text
tenant-a
tenant-b
platform
```

Executor chạy trong `platform` namespace và chỉ được cấp quyền theo Role/RoleBinding cần thiết để thao tác target namespace đã cho phép.

### Consequences

- Pro: Dễ demo và dễ test cross-tenant deny.
- Pro: Phù hợp Kubernetes RBAC native.
- Pro: Scope vừa đủ cho capstone.
- Trade-off: Không mạnh bằng account/cluster-per-tenant isolation.
- Trade-off: Cần cẩn thận RoleBinding để tránh cấp quyền quá rộng.

### Alternatives considered

- Cluster-per-tenant: isolation mạnh nhưng quá nặng cho capstone.
- Shared namespace + label isolation: đơn giản nhưng khó chứng minh deny cross-tenant.

---

## ADR-004 - Chọn S3 Object Lock cho audit trail

- **Status:** Accepted, pending trainer confirmation for implementation depth
- **Date:** 2026-06-23

### Context

TF3 yêu cầu audit log tamper-evident, retention tối thiểu 90 ngày. AI deployment contract cũng ghi audit target là S3 Object Lock Compliance Mode.

### Decision

CDO-02 chọn S3 Object Lock làm audit storage target. Audit record sẽ được ghi theo `correlation_id`, bao gồm alert, detect, decide, safety, dry-run, execute, verify, rollback/escalate.

### Consequences

- Pro: Khớp hard requirement và AI contract.
- Pro: Dễ query bằng Athena hoặc inspect object.
- Pro: Có retention rõ ràng.
- Trade-off: Setup Object Lock cần tạo bucket đúng cấu hình từ đầu.
- Trade-off: Cost cao hơn log local hoặc CloudWatch-only.

### Alternatives considered

- CloudWatch Logs only: dễ triển khai nhưng tamper-evident yếu hơn.
- Append-only database: query tốt nhưng cần build thêm storage logic.

---

## ADR-005 - Chọn CloudWatch + Prometheus-compatible metrics + OpenTelemetry schema

- **Status:** Accepted
- **Date:** 2026-06-23

### Context

AI telemetry contract yêu cầu metrics, logs và traces: `service_error_rate`, `service_latency_p95`, `container_resource_usage`, `application_log_event`, `distributed_trace_error_event`.

### Decision

CDO-02 chọn observability stack theo hướng:

- CloudWatch Logs cho logs.
- Container Insights/Prometheus-compatible metrics cho metrics.
- OpenTelemetry schema tương thích Jaeger hoặc AWS X-Ray cho traces.
- Với RE2/RE3 Offline Simulation Mode, dùng telemetry preprocessor đọc `metrics.csv`, `logs.csv`, `traces.csv`, inject tenant UUID, chuẩn hóa signal và đưa vào executor/AI API path. SQS chỉ là buffer nội bộ nếu CDO chọn, vì AI contract mới chưa cung cấp queue ARN.

W11 Pack #1 tập trung design/schema; W12 mới thu evidence thật từ sandbox hoặc simulation.

### Consequences

- Pro: Khớp telemetry contract của AI.
- Pro: Dễ tích hợp với AWS/EKS.
- Pro: Có thể demo logs/metrics trước, traces bổ sung nếu kịp.
- Trade-off: Triển khai đủ traces có thể tốn thời gian.
- Trade-off: Cần normalize telemetry trước khi gọi AI.
- Trade-off: Cần build preprocessor và có thể thêm SQS buffer nội bộ nếu replay volume cao.

### Alternatives considered

- CloudWatch-only: đơn giản hơn nhưng không đáp ứng trace signal đầy đủ.
- Full Prometheus/Grafana/Jaeger stack: mạnh nhưng nhiều moving parts cho capstone.

---

## ADR-006 - Chọn DynamoDB conditional write cho idempotency lock

- **Status:** Accepted
- **Date:** 2026-06-24

### Context

AI API Contract yêu cầu `Idempotency-Key` cho các request thay đổi trạng thái như `/v1/decide` và `/v1/verify`. Deployment Contract cũng mô tả nhu cầu idempotency lock để tránh execute cùng một action nhiều lần khi có retry hoặc lỗi mạng.

### Decision

CDO-02 chọn **DynamoDB conditional write** làm cơ chế idempotency lock mặc định. Mỗi action sẽ ghi lock theo `Idempotency-Key`; nếu key đã tồn tại, CDO từ chối execute trùng và ghi audit.

### Consequences

- Pro: AWS-native, phù hợp với kiến trúc trên AWS.
- Pro: Conditional write rõ ràng để chống race condition.
- Pro: Dễ audit và debug theo key.
- Trade-off: Cần thêm DynamoDB table và IAM permission.
- Trade-off: Với demo nhỏ, Redis/local lock có thể đơn giản hơn nhưng kém bền hơn.

### Alternatives considered

- Redis lock TTL: nhanh, đơn giản nhưng cần thêm runtime dependency.
- In-memory lock: dễ làm nhất nhưng không an toàn khi executor restart hoặc scale nhiều replicas.

---

## ADR-007 - Chấp nhận Mock Mode cho RE2/RE3 Offline Simulation

- **Status:** Accepted, pending trainer evidence confirmation
- **Date:** 2026-06-24

### Context

AI API Contract và Deployment Contract xác định RE2/RE3 là dataset offline tĩnh. Vì vậy luồng execute action như `RESTART_DEPLOYMENT` hoặc `SCALE_REPLICAS` sẽ chạy ở dạng giả lập: CDO ghi nhận action giả định, sau đó gửi `post_telemetry_window` từ dataset sang `/v1/verify`.

### Decision

CDO-02 chấp nhận **Mock Mode** cho luồng RE2/RE3 offline simulation để align với AI contract. Nếu trainer yêu cầu demo action thật, CDO-02 sẽ bổ sung một sandbox Kubernetes scenario riêng, nhưng không xem đó là nguồn verify chính cho RE2/RE3 dataset.

### Consequences

- Pro: Khớp contract AI và dataset offline.
- Pro: Giảm rủi ro build khi chưa có full live telemetry.
- Pro: Dễ tạo repeatable test scenario.
- Trade-off: Demo có thể bị xem là ít "real" hơn action thật trên Kubernetes.
- Trade-off: Cần giải thích rõ difference giữa simulation evidence và live sandbox evidence.

### Alternatives considered

- Action thật trên Kubernetes cho toàn bộ flow: thuyết phục hơn nhưng khó khớp RE2/RE3 offline telemetry.
- Chỉ dùng mock endpoint không có dataset: dễ làm nhưng evidence yếu hơn.

---

## ADR-008 - Chọn GitOps path (ArgoCD PR) cho `pattern_type: deferred`

- **Status:** Accepted
- **Date:** 2026-06-25

### Context

AI API Contract (commit 86b32e7) chốt rõ hai luồng xử lý dựa trên `pattern_type`:
- `"urgent"`: action khẩn cấp, CDO execute trực tiếp Kubernetes API.
- `"deferred"`: action tích lũy cấu hình (ví dụ SCALE_REPLICAS do queue_backlog), CDO **bắt buộc** không direct mutate Kubernetes mà phải tạo Git commit/PR để ArgoCD sync.

CDO-02 cần quyết định cụ thể cách implement path `"deferred"`.

### Decision

CDO-02 implement `pattern_type: "deferred"` bằng cách executor tự động tạo Git commit (hoặc PR nếu cần review) cập nhật manifest/Helm values, sau đó ArgoCD phát hiện thay đổi và sync về cluster. CDO không gọi Kubernetes API trực tiếp trong path này.

### Consequences

- Pro: Khớp AI contract, tránh state drift giữa Git và cluster.
- Pro: ArgoCD drift detection đảm bảo cluster luôn khớp Git.
- Pro: Có audit trail rõ (Git commit history + ArgoCD sync history).
- Trade-off: Latency cao hơn path `"urgent"` (Git commit + ArgoCD sync ~2-5 phút).
- Trade-off: CDO executor cần có quyền write vào Git repo và ArgoCD phải được cấu hình watch manifest repo.

### Alternatives considered

- Không implement deferred path: đơn giản hơn nhưng vi phạm AI contract.
- Manual PR workflow: có approval gate nhưng quá chậm cho self-heal automation.
