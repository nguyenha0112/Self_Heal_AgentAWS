# Architecture Decision Records - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Ready for W11 Pack #1 review  
**Cập nhật lần cuối:** 2026-06-23  

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

AI contract định nghĩa `/v1/detect`, `/v1/decide`, `/v1/verify` và trả `action_plan[]`. Deployment contract hiện có chi tiết cần clarify vì nhắc AI có thể fetch kubeconfig/gọi EKS API. Nếu AI trực tiếp mutate Kubernetes, CDO khó enforce safety, RBAC và audit nhất quán.

### Decision

CDO-02 chọn boundary: **AI chỉ decide, CDO executor mới execute**. AI trả action plan; CDO validate tenant, namespace, blast-radius, rollback plan, verify plan rồi mới execute hoặc deny/escalate.

### Consequences

- Pro: Rõ ownership giữa AI và CDO.
- Pro: CDO kiểm soát được zero unsafe action.
- Pro: Audit log tập trung qua CDO executor.
- Trade-off: CDO phải build executor/safety gate đầy đủ.
- Trade-off: Cần negotiate lại nếu AI muốn giữ kubeconfig.

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

AI telemetry contract yêu cầu metrics, logs và traces: `istio_request_error_rate`, `istio_request_latency_p95`, `container_memory_working_set_bytes`, `app_log_error_event`, `trace_span_error_event`.

### Decision

CDO-02 chọn observability stack theo hướng:

- CloudWatch Logs cho logs.
- Container Insights/Prometheus-compatible metrics cho metrics.
- OpenTelemetry schema tương thích Jaeger hoặc AWS X-Ray cho traces.
- Với RE2/RE3 Offline Simulation Mode, dùng telemetry preprocessor đọc `metrics.csv`, `logs.csv`, `traces.csv`, inject `tenant_id`, chuẩn hóa signal và emit qua SQS theo contract AI.

W11 Pack #1 tập trung design/schema; W12 mới thu evidence thật từ sandbox hoặc simulation.

### Consequences

- Pro: Khớp telemetry contract của AI.
- Pro: Dễ tích hợp với AWS/EKS.
- Pro: Có thể demo logs/metrics trước, traces bổ sung nếu kịp.
- Trade-off: Triển khai đủ traces có thể tốn thời gian.
- Trade-off: Cần normalize telemetry trước khi gọi AI.
- Trade-off: Cần build preprocessor/SQS flow cho dataset simulation.

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

AI API Contract và Deployment Contract xác định RE2/RE3 là dataset offline tĩnh. Vì vậy luồng execute action như `RESTART_DEPLOYMENT` hoặc `SCALE_UP_PODS` sẽ chạy ở dạng giả lập: CDO ghi nhận action giả định, sau đó gửi `post_telemetry_window` từ dataset sang `/v1/verify`.

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
