# Self-Heal Runtime Runbook

Tài liệu này mô tả những việc hệ thống Self-Heal sẽ làm để phát hiện, quyết định, thực thi, xác thực và ghi audit một hành động tự chữa lỗi. Nội dung bám theo các tài liệu trong `docs/` và 3 contract đã ký với team AI:

- `ai-api-contract.md`
- `deployment-contract.md`
- `telemetry-contract.md`

## 1. Nguyên tắc vận hành

Self-Heal Engine không phải là hệ thống "AI tự sửa Kubernetes". Boundary đã chốt là:

```text
AI Engine = detect + decide + verify
CDO Executor = validate + execute + rollback/escalate + audit
```

AI chỉ trả về phân tích và `action_plan`. CDO Executor là thành phần duy nhất được quyền thay đổi Kubernetes hoặc GitOps manifest, và chỉ làm sau khi qua các lớp kiểm tra an toàn.

Các nguyên tắc bắt buộc:

- Không cho AI giữ kubeconfig hoặc gọi Kubernetes API.
- Không execute nếu thiếu `verify_policy`, target namespace không hợp lệ, action không nằm trong allow-list, hoặc confidence không đủ.
- Mọi mutating action phải có rollback snapshot do CDO tự capture trước khi execute.
- Mọi incident phải trace được bằng `correlation_id`.
- Mọi request sang AI phải có `X-Tenant-Id`, `Idempotency-Key`, `X-Dry-Run-Mode`.
- DynamoDB idempotency lock chỉ áp dụng cho `/v1/decide`, nơi có nguy cơ dẫn tới thay đổi hạ tầng.
- Khi không chắc chắn, hệ thống fail-safe: deny hoặc escalate, không mutate bừa.

## 2. Các thành phần tham gia

| Thành phần | Vai trò |
|---|---|
| Telemetry collectors | Thu logs, metrics, traces từ workload/Kubernetes. |
| Telemetry forwarder | Chuẩn hóa, scrub PII/secret, validate schema, batch-push sang AI `/v1/detect`. |
| AI Engine | Phát hiện bất thường, match runbook, trả action plan, verify kết quả. |
| CDO Executor | Điều phối toàn bộ loop self-heal và gọi Kubernetes/GitOps khi được phép. |
| Pre-Decide Gate | Quyết định có nên đi tiếp từ detect sang decide không. |
| Safety Gate | Quyết định action AI đề xuất có an toàn để execute không. |
| Kubernetes API | Được CDO Executor dùng cho urgent path. |
| ArgoCD | Đồng bộ manifest từ Git cho deferred path. |
| Kyverno | Admission control chặn giá trị nguy hiểm ở cluster level. |
| DynamoDB | Idempotency lock chống execute trùng. |
| S3 Object Lock | Audit trail tamper-evident, retention tối thiểu 90 ngày. |

## 3. Luồng tổng quát

```text
Telemetry / Alert
  -> normalize + scrub + validate
  -> POST /v1/detect
  -> Pre-Decide Gate
  -> POST /v1/decide
  -> Idempotency Lock
  -> Safety Gate
  -> Capture rollback snapshot
  -> Execute urgent hoặc deferred action
  -> Collect post-action telemetry
  -> POST /v1/verify
  -> DONE / RETRY / ROLLBACK / ESCALATE
  -> Audit flush
```

## 4. Telemetry đầu vào

CDO thu thập và chuẩn hóa telemetry theo `telemetry-contract.md`. Mỗi điểm dữ liệu phải có:

- `ts`: timestamp RFC3339 UTC, độ chính xác millisecond.
- `tenant_id`: UUID của tenant.
- `service`: tên service phát sinh tín hiệu.
- `signal_name`: một trong các enum đã ký.
- `value`: giá trị metric hoặc message event/log.
- `labels.system`: bắt buộc nếu có `labels`.
- `labels.namespace`, `labels.deployment`: nên có để map đúng Kubernetes target.

Các signal hệ thống dùng để heal:

| Signal | Ý nghĩa | Hành động thường gặp |
|---|---|---|
| `pod_oom_event` | Pod/container bị OOMKilled. | `PATCH_MEMORY_LIMIT` |
| `container_resource_usage` | Memory/cpu usage cao, nguy cơ OOM. | `PATCH_MEMORY_LIMIT` hoặc escalate |
| `container_restart_count` | Container restart nhiều lần, CrashLoopBackOff. | `RESTART_DEPLOYMENT` hoặc `ROLLOUT_UNDO` |
| `service_unhealthy` | Readiness/liveness probe fail. | `RESTART_DEPLOYMENT` |
| `service_latency_p95` | Latency spike/service stuck. | `RESTART_DEPLOYMENT` |
| `service_error_rate` | Tỷ lệ lỗi tăng. | `RESTART_DEPLOYMENT` hoặc escalate |
| `application_log_event` | Log lỗi/stack trace đã scrub. | Hỗ trợ diagnose, có thể restart/escalate |
| `distributed_trace_error_event` | Trace span lỗi trong giao dịch phân tán. | Hỗ trợ diagnose/escalate |
| `queue_backlog` | Hàng đợi tồn đọng cao. | `SCALE_REPLICAS` qua GitOps |
| `db_connection_pool_saturation` | Pool DB cạn kiệt. | Scale/restart/escalate tùy runbook |
| `secret_expiry_warning` | Secret/cert sắp hết hạn. | `ROTATE_SECRET` qua GitOps |

Nếu telemetry sai schema, thiếu trường bắt buộc, sai `tenant_id`, hoặc chứa dữ liệu nhạy cảm chưa scrub:

```text
Reject -> đưa vào DLQ -> ghi audit/metric -> alert nếu malformed > 0.5% trong 5 phút
```

## 5. Bước 1: Detect

CDO gọi AI:

```text
POST /v1/detect
```

Request bắt buộc:

- `idempotency_key`
- `dry_run_mode`
- `telemetry_window[]`
- `correlation_id` nếu đã có

Headers bắt buộc:

```text
X-Tenant-Id: <tenant_uuid>
Idempotency-Key: <uuid>
X-Dry-Run-Mode: "true" | "false"
X-Correlation-Id: <uuid nếu có>
```

AI trả về:

- `anomaly_detected`
- `severity`
- `confidence`
- `reasoning`
- `correlation_id`
- `anomaly_context` nếu có lỗi

CDO ghi audit:

```text
alert_received
telemetry_normalized
telemetry_buffered
detect_called
detect_response_received
```

## 6. Bước 2: Pre-Decide Gate

Pre-Decide Gate chạy sau `/v1/detect`, trước `/v1/decide`. Mục tiêu là hỏi: "Có nên để hệ thống tự xử lý incident này không?"

| Điều kiện | Quyết định | Audit reason |
|---|---|---|
| `anomaly_detected=false` | Đóng incident, no action. | `no_anomaly` |
| `confidence < 0.5` | Discard, coi là noise. | `low_confidence_discard` |
| `confidence 0.5-0.79` và severity LOW/MEDIUM | Log warning, không execute. | `low_confidence_no_action` |
| `confidence 0.5-0.79` và severity HIGH/CRITICAL | Escalate ngay. | `low_confidence_escalated` |
| Cùng service flapping lần 3+ trong 10 phút | Escalate. | `flapping_escalated` |
| Maintenance window active | Suppress. | `maintenance_suppressed` |
| `confidence >= 0.8` và severity MEDIUM/HIGH/CRITICAL | Gọi `/v1/decide`. | `proceed_to_decide` |

CDO không tự filter theo fault type. Nếu AI không match được pattern, AI phải trả confidence thấp hoặc action không hợp lệ để CDO gate chặn.

## 7. Bước 3: Decide

CDO gọi AI:

```text
POST /v1/decide
```

Request bắt buộc:

- `correlation_id`
- `idempotency_key`
- `dry_run_mode`
- `anomaly_context`: full object từ detect response

AI trả về:

- `matched_runbook`
- `pattern_type`: `urgent` hoặc `deferred`
- `action_plan[]`
- `blast_radius_config`
- `verify_policy`
- `correlation_id`
- `idempotency_key`
- `dry_run_mode`
- `cost_cap_exceeded` nếu có

Action allow-list:

```text
RESTART_DEPLOYMENT
PATCH_MEMORY_LIMIT
SCALE_REPLICAS
ROLLOUT_UNDO
ROTATE_SECRET
```

Các action ngoài danh sách này, ví dụ `DELETE_NAMESPACE`, `DELETE_POD`, `MODIFY_IAM`, phải bị deny.

## 8. Bước 4: Idempotency Lock

Trước khi execute mutating action, CDO ghi lock vào DynamoDB:

```text
PutItem ConditionExpression: attribute_not_exists(idempotency_key)
```

Nếu lock thành công:

```text
idempotency_lock_acquired -> tiếp tục Safety Gate
```

Nếu lock đã tồn tại:

```text
idempotency_duplicate_denied -> không execute lại
```

TTL khuyến nghị là 24 giờ để tránh replay cùng incident trong cùng ngày vận hành.

## 9. Bước 5: Safety Gate

Safety Gate chạy sau `/v1/decide`, trước bất kỳ thay đổi nào. Mục tiêu là hỏi: "Action này có an toàn để execute không?"

Các kiểm tra bắt buộc:

| Check | Rule |
|---|---|
| Tenant match | `tenant_id` phải khớp namespace target. |
| Namespace allow-list | Target namespace phải nằm trong `allowed_namespaces`. |
| Action allow-list | Action phải thuộc 5 enum đã ký. |
| Pattern routing | `urgent` mới được direct Kubernetes API; `deferred` bắt buộc GitOps. |
| Blast radius | Không vượt số pod/replica/deployment cho phép. |
| Memory cap | `PATCH_MEMORY_LIMIT` không vượt cap, ví dụ 4Gi trong sandbox. |
| Replica cap | `SCALE_REPLICAS` không vượt cap, ví dụ 10 replicas. |
| Rollback plan | Mutating action phải có snapshot trước execute. |
| Verify policy | `verify_policy.window_seconds` phải tồn tại. |
| Dry-run | Urgent path phải server-side dry-run trước execute thật. |
| Cost cap | Nếu `cost_cap_exceeded=true`, ghi warning nhưng vẫn có thể execute nếu safety pass. |

Nếu gate fail:

```text
safety_denied -> execute_skipped -> escalated hoặc incident_closed tùy case
```

Các reason thường gặp:

- `denied_cross_tenant`
- `denied_action_not_allowed`
- `blast_radius_exceeded`
- `missing_verify_policy`
- `missing_rollback_path`
- `tenant_mismatch`
- `dry_run_failed`

## 10. Bước 6A: Urgent Path

`pattern_type="urgent"` dùng cho sự cố cần sửa nhanh, RTO mục tiêu dưới 60 giây. CDO được phép gọi Kubernetes API trực tiếp sau khi safety pass.

Các action urgent:

| Action | Hệ thống làm gì |
|---|---|
| `RESTART_DEPLOYMENT` | Patch annotation `kubectl.kubernetes.io/restartedAt` để rolling restart Deployment. |
| `PATCH_MEMORY_LIMIT` | Patch resources memory request/limit cho container target. |
| `ROLLOUT_UNDO` | Rollback Deployment về ReplicaSet revision trước. |

Quy trình urgent:

```text
1. Capture rollback snapshot từ Kubernetes API:
   - replica_count
   - image_tag
   - memory_limit
   - deployment revision

2. Lưu snapshot vào audit.

3. Server-side dry-run:
   - nếu fail -> không execute thật, audit dry_run_failed, escalate.

4. Execute thật qua Kubernetes API.

5. Ghi action_executed:
   - action
   - target
   - status COMPLETED hoặc FAILED
   - execution_time_seconds

6. Chờ verify_policy.window_seconds, có cap nội bộ để không chờ vô hạn.

7. Scrape post-action telemetry.

8. Gọi /v1/verify.
```

Ví dụ OOM:

```text
pod_oom_event
-> AI detect OOM_KILL
-> AI decide PATCH_MEMORY_LIMIT deployment/cdo-sample-api memory_limit_mb=1024
-> CDO safety pass
-> CDO dry-run patch
-> CDO patch Deployment
-> Pod rollout lại
-> Verify healthy
-> incident_closed auto_resolved
```

## 11. Bước 6B: Deferred Path

`pattern_type="deferred"` dùng cho thay đổi cấu hình dài hạn, cần giữ Git là source of truth. CDO không được direct mutate Kubernetes trong path này.

Các action deferred:

| Action | Hệ thống làm gì |
|---|---|
| `SCALE_REPLICAS` | Tạo Git commit/PR sửa replicas trong manifest; ArgoCD sync. |
| `ROTATE_SECRET` | Tạo Git commit/PR hoặc cập nhật secret rotation manifest theo allow-list; ArgoCD sync. |

Quy trình deferred:

```text
1. Capture rollback snapshot:
   - Git commit SHA hiện tại
   - nội dung manifest trước khi patch

2. Safety Gate validate tenant, namespace, action, blast-radius, verify_policy.

3. Executor tạo Git commit hoặc PR vào đúng path tenant.

4. ArgoCD sync Application tương ứng.

5. Executor poll ArgoCD:
   - Sync Status = Synced
   - Health Status = Healthy

6. Ghi action_executed status COMPLETED nếu sync thành công.

7. Thu post-action telemetry.

8. Gọi /v1/verify.
```

Nếu ArgoCD sync fail, timeout, hoặc verify regression:

```text
revert manifest về snapshot trước đó -> commit revert -> ArgoCD sync -> escalate
```

## 12. Bước 7: Verify

CDO gọi AI:

```text
POST /v1/verify
```

Request bắt buộc:

- `correlation_id`
- `idempotency_key`
- `dry_run_mode`
- `action_executed`
- `post_telemetry_window[]`

AI trả về:

- `success`
- `regression_detected`
- `next_action`: `DONE`, `RETRY`, `ROLLBACK`, `ESCALATE`
- `escalation_bundle` nếu cần

CDO xử lý:

| `next_action` | CDO làm gì |
|---|---|
| `DONE` | Ghi `incident_closed` với `result=auto_resolved`. |
| `RETRY` | Retry theo policy, dùng cùng context và audit rõ `retrying`. |
| `ROLLBACK` | Dùng snapshot đã capture trước execute để khôi phục. |
| `ESCALATE` | Gửi bundle cho người trực, không execute thêm. |

## 13. Rollback

Rollback không lấy từ AI. CDO tự capture snapshot trước execute và chịu trách nhiệm restore.

Urgent rollback:

| Action trước đó | Rollback |
|---|---|
| `RESTART_DEPLOYMENT` | Không nhất thiết rollback nếu chỉ restart; nếu phát sinh regression thì rollout undo hoặc escalate. |
| `PATCH_MEMORY_LIMIT` | Patch lại memory request/limit từ snapshot. |
| `ROLLOUT_UNDO` | Rollout lại revision đã lưu nếu còn an toàn. |

Deferred rollback:

```text
1. Lấy manifest snapshot hoặc Git SHA trước patch.
2. Tạo revert commit.
3. Chờ ArgoCD sync về trạng thái cũ.
4. Ghi rollback_done hoặc escalated nếu revert fail.
```

Nếu rollback không an toàn hoặc thiếu dữ liệu:

```text
escalated -> kèm logs, metrics, snapshot, action đã thử, correlation_id
```

## 14. Escalation

Escalation xảy ra khi hệ thống không thể tự heal an toàn:

- AI timeout hoặc 503.
- AI response sai schema.
- Confidence thấp nhưng severity cao.
- Flapping nhiều lần.
- Safety Gate deny.
- Dry-run fail.
- Kubernetes API execute fail.
- ArgoCD sync fail hoặc timeout.
- Verify trả `ESCALATE`.
- Verify regression nhưng rollback không an toàn.
- Audit sink fail.

Escalation bundle cần có:

- `correlation_id`
- `tenant_id`
- namespace/deployment target
- signal kích hoạt
- AI reasoning
- action plan đã nhận
- safety decision
- dry-run result
- execution result nếu có
- logs gần nhất
- metrics/post-telemetry
- rollback snapshot hoặc lý do thiếu snapshot

## 15. Audit trail bắt buộc

Mỗi incident cần có chuỗi audit đầy đủ theo `correlation_id`.

Events tối thiểu:

```text
alert_received
telemetry_normalized
telemetry_buffered
detect_called
detect_response_received
pre_decide_decision
idempotency_lock_acquired / idempotency_duplicate_denied
decide_called
action_plan_received
safety_passed / safety_denied
rollback_snapshot_captured
dry_run_done / dry_run_failed
execute_done / execute_skipped
verify_called
verify_done
rollback_done / escalated / incident_closed
```

Fields tối thiểu:

| Field | Ý nghĩa |
|---|---|
| `timestamp` | Thời điểm audit event. |
| `correlation_id` | Trace toàn bộ incident. |
| `tenant_id` | Tenant bị ảnh hưởng. |
| `namespace` | Namespace target. |
| `action_type` | Action AI đề xuất hoặc CDO execute. |
| `decision` | allow, deny, execute, rollback, escalate. |
| `result` | success, failed, denied, skipped, auto_resolved. |
| `reason` | Machine-readable reason. |
| `idempotency_key` | Key chống duplicate execution. |

Audit storage mục tiêu:

```text
S3 Object Lock Governance Mode
Retention >= 90 ngày
Key pattern: audit/<tenant_id>/<correlation_id>.json
```

## 16. Các runbook heal chính

### 16.1 OOM / Memory Pressure

Trigger:

- `pod_oom_event`
- `container_resource_usage` vượt ngưỡng

Expected action:

```text
PATCH_MEMORY_LIMIT
```

Luồng:

```text
Detect OOM -> Decide PATCH_MEMORY_LIMIT -> Safety memory cap <= 4Gi
-> Capture current memory limit -> Dry-run patch -> Patch Deployment
-> Wait rollout -> Verify pod ready/restart stable/memory dưới ngưỡng
```

Auto-resolved khi:

- Deployment rollout thành công.
- Pod mới Ready.
- Không còn OOM signal trong post telemetry.
- `/v1/verify` trả `DONE`.

Rollback khi:

- Verify regression.
- Pod tiếp tục OOM sau patch.
- Patch gây workload degraded.

### 16.2 Service Stuck / Latency Spike / Unhealthy

Trigger:

- `service_latency_p95`
- `service_unhealthy`
- `service_error_rate`

Expected action:

```text
RESTART_DEPLOYMENT
```

Luồng:

```text
Detect latency/unhealthy -> Decide restart
-> Safety tenant/action/blast-radius
-> Capture Deployment revision/image/replicas
-> Dry-run restart patch -> Execute restart
-> Verify readiness, error rate, latency
```

Escalate khi:

- Error rate vẫn cao.
- Readiness vẫn fail.
- Incident flapping lần 3 trong 10 phút.

### 16.3 CrashLoop / Bad Deploy

Trigger:

- `container_restart_count`
- `service_unhealthy`
- `application_log_event`

Expected action:

```text
ROLLOUT_UNDO
```

Luồng:

```text
Detect restart loop -> Decide rollback
-> Safety target namespace/revision
-> Capture current revision
-> Dry-run rollback patch nếu có thể
-> Rollout undo
-> Verify pod Ready/restart count không tăng
```

Escalate khi:

- Không có previous ReplicaSet revision.
- Rollback không làm service healthy.

### 16.4 Queue Backlog

Trigger:

```text
queue_backlog
```

Expected action:

```text
SCALE_REPLICAS
pattern_type: deferred
```

Luồng:

```text
Detect queue backlog -> Decide SCALE_REPLICAS deferred
-> Safety replicas <= cap, namespace allow-list
-> Capture Git SHA + manifest snapshot
-> Commit replicas change
-> ArgoCD sync
-> Verify backlog giảm, pods healthy
```

Không được:

```text
kubectl scale trực tiếp trong deferred path
```

### 16.5 Secret / Certificate Expiry

Trigger:

```text
secret_expiry_warning
```

Expected action:

```text
ROTATE_SECRET
pattern_type: deferred
```

Luồng:

```text
Detect secret expiry -> Decide ROTATE_SECRET
-> Safety secret_name allow-list
-> Capture Git SHA/manifest snapshot
-> Commit rotation manifest/config
-> ArgoCD sync
-> Verify service ready và secret mới hợp lệ
```

Escalate khi:

- Secret không nằm trong allow-list.
- Không có verify policy.
- Rotation ảnh hưởng readiness.

## 17. Các lớp bảo vệ

Hệ thống không phụ thuộc một lớp duy nhất.

```text
CDO Safety Gate
  -> Kubernetes RBAC
  -> Kyverno Admission Webhook
  -> Audit + rollback
```

| Lớp | Chặn được gì |
|---|---|
| Safety Gate | Sai tenant, sai action, thiếu verify/rollback, vượt blast-radius. |
| RBAC | Executor không có verb/resource nguy hiểm. |
| Kyverno | Giá trị nguy hiểm như replicas quá cao, memory quá lớn, namespace ngoài allow-list. |
| ArgoCD AppProject | Deferred path không sync chéo tenant. |
| Idempotency Lock | Retry không execute trùng. |
| Circuit Breaker | Quá nhiều failure thì dừng automation. |

## 18. Xử lý lỗi AI/API

| HTTP code | CDO xử lý |
|---|---|
| `400` | Không retry. Log/audit. Nếu là telemetry thì đưa DLQ. |
| `401` | Không retry. Kiểm tra Local Trust/mTLS/NetworkPolicy. |
| `403` | Tenant mismatch. Không retry. Audit `tenant_mismatch`. |
| `409` | Duplicate idempotency. Không execute lại. |
| `429` | Backoff theo `Retry-After`. |
| `500` | Retry tối đa 2 lần với backoff 1s, 3s; fail thì escalate. |
| `503` | AI unavailable. Không execute mặc định; escalate + audit. |

## 19. Nghiệm thu một incident auto-heal

Một incident chỉ được tính auto-resolved khi có đủ:

- Có `correlation_id` xuyên suốt detect/decide/execute/verify.
- `/v1/detect` phát hiện anomaly với confidence đủ qua Pre-Decide Gate.
- `/v1/decide` trả action hợp lệ, có `verify_policy`.
- Idempotency lock acquired.
- Safety Gate pass.
- Snapshot rollback được capture trước execute.
- Dry-run pass nếu urgent.
- Execute thành công.
- `/v1/verify` trả `next_action=DONE`.
- Audit có `incident_closed result=auto_resolved`.

Nếu thiếu một trong các điểm trên, incident không nên tính là auto-resolved; phải tính là denied, rolled back hoặc escalated.

## 20. Nghiệm thu an toàn toàn hệ thống

Các tiêu chí pass cho test window:

- Chạy ít nhất 10 scenarios.
- Simulation window tối thiểu 4 giờ.
- Auto-resolve rate >= 60%.
- Unsafe action count = 0.
- Cross-tenant mutation = 0.
- Audit coverage = 100%.
- Mọi mutating action đều có safety/dry-run/verify/rollback evidence.
- Với deferred path, có Git commit/ArgoCD sync evidence.
- Với urgent path, có Kubernetes API result và post-action telemetry.

## 21. Checklist vận hành trước khi bật automation

- AI endpoint reachable trong cluster: `http://ai-engine.self-heal-system.svc.cluster.local:8080`.
- Executor ServiceAccount/RBAC đúng namespace và không dùng cluster-admin.
- NetworkPolicy chỉ cho executor gọi AI.
- DynamoDB idempotency table available.
- S3 audit bucket Object Lock enabled.
- Prometheus/Grafana/OTel hoặc telemetry source hoạt động.
- DLQ và malformed telemetry alarm hoạt động.
- ArgoCD Application theo tenant đang Healthy/Synced.
- Kyverno policies đang Enforce.
- Secret/Git credentials không hardcode trong repo/log.
- Runbook rollback cho từng action đã test.

