# Câu Hỏi Còn Lại Cho AI Team - TF3 CDO-02

Tài liệu này ghi các câu hỏi CDO-02 đã hỏi AI team và trạng thái hiện tại sau khi đối chiếu contract-new-2 (2026-06-25).

> **Mentor feedback**: "12 câu hỏi vẫn mở với AI team → I/O schema chưa chốt"
> **Cập nhật**: Contract-new-2 đã chốt I/O schema. Xem Section tổng kết bên dưới.

---

## 1. Mock API chính thức

✅ **Resolved (contract-new-2)**

Base URL nội bộ cluster:
```text
http://ai-engine.self-heal-system.svc.cluster.local:8080/
```

Endpoints:
```text
POST /v1/detect
POST /v1/decide
POST /v1/verify
GET  /health
GET  /ready
GET  /metrics
```

Auth: **Local Trust + K8s NetworkPolicy** — không cần SigV4. Required headers:
```text
X-Tenant-Id: 6c8b4b2b-4d45-4209-a1b4-4b532d56a31c
Idempotency-Key: UUID v4
X-Dry-Run-Mode: "true" | "false"
X-Correlation-Id: UUID v4 (required cho decide/verify)
```

---

## 2. Tenant ID chính thức

✅ **Resolved (contract-new-2, deployment contract section tenant mapping)**

CDO-02 dùng UUID:
```text
6c8b4b2b-4d45-4209-a1b4-4b532d56a31c
```
Gắn vào `X-Tenant-Id` header và `tenant_id` trong telemetry payload.

---

## 3. Evidence W11/W12 có được chấp nhận không?

⏳ **Cần trainer/mentor confirm**

CDO hiện đã có:
- App public `podinfo` chạy thật trên AWS EKS.
- Logs, health check, readiness check, Prometheus metrics thật.
- Action thật `RESTART_DEPLOYMENT` bằng Kubernetes rollout restart.
- Mock payload đúng contract cho `/v1/detect`, `/v1/decide`, `/v1/verify`.

AI/trainer xác nhận setup này có đủ cho W11/W12 evidence không, hay AI yêu cầu thêm một app business đầy đủ hơn?

---

## 4. `pattern_type=deferred`

✅ **Resolved (contract-new-2 Section 3.2)**

- `urgent`: CDO execute Kubernetes trực tiếp sau safety gate (RESTART_DEPLOYMENT, PATCH_MEMORY_LIMIT, ROLLOUT_UNDO).
- `deferred`: CDO tạo Git commit/PR → ArgoCD sync; **không** gọi Kubernetes API trực tiếp (SCALE_REPLICAS, ROTATE_SECRET).

---

## 5. Ngưỡng confidence

✅ **Resolved — CDO tự own**

Contract-new-2 không đặt ngưỡng bắt buộc → CDO-02 chốt policy nội bộ: `confidence >= 0.8` → gọi `/v1/decide` và execute; `< 0.8` → escalate + audit, không execute. Configurable qua config file.

---

## 6. Enum `suspected_fault_type`

⏳ **Skip tạm thời — làm việc với AI team sáng mai (2026-06-26)**

Contract-new-2 cho ví dụ: `"database_connection_failure"`. Chưa có exhaustive enum list. Tạm thời CDO không whitelist cứng — dùng giá trị từ AI response làm key để map fallback runbook, tránh reject response hợp lệ. Sẽ chốt danh sách sau khi sync với AI team.

---

## 7. Coverage của mock response

✅ **Resolved (contract-new-2 schema)**

Contract-new-2 có schema example đầy đủ cho 5 actions:
```text
RESTART_DEPLOYMENT
PATCH_MEMORY_LIMIT
SCALE_REPLICAS
ROLLOUT_UNDO
ROTATE_SECRET
```
Tất cả 5 action đều được demo thật (build-real) — không có action design-only.

---

## 8. Policy cho `ROTATE_SECRET`

✅ **Resolved (contract-new-2)**

- Trigger: `secret_expiry_warning` signal.
- `pattern_type: "deferred"` — GitOps path, không direct mutate.
- Required params: `secret_name` trong `action_plan[].params`.
- Verify policy: bắt buộc `verify_policy.window_seconds` — CDO chờ verify sau rotate.
- Safety gate: `secret_name` phải nằm trong allow-list đã định nghĩa.
- Rollback: nếu verify fail, escalate (không rollback secret tự động — secret rotation là one-way).

---

## 9. SQS ownership

✅ **Resolved (telemetry contract-new-2 Section 2.5.C)**

- SQS là **CDO-internal buffer**. AI không pull từ SQS.
- AI-CDO interface chính là HTTP API `/v1/detect`, `/v1/decide`, `/v1/verify`.
- CDO Forwarder/Worker batch-push từ SQS sang `/v1/detect`.

---

## 10. Topology registry

✅ **Resolved (contract-new-2)**

Format action target là **string**: `"deployment/<name>"` với namespace qua `params.namespace`:
```json
{
  "action": "RESTART_DEPLOYMENT",
  "target": "deployment/cdo-sample-api",
  "params": { "namespace": "tenant-a" }
}
```
CDO map dựa trên: service → namespace → deployment (explicit mapping, không dùng implicit pod name).

---

## 11. Fallback runbook

✅ **Resolved — CDO tự own**

AI không cung cấp static runbook. CDO chốt policy nội bộ: khi AI timeout/503/cost cap/response invalid → escalate + audit, không execute mặc định. CDO owns static escalation policy; gửi AI review nếu cần bổ sung.

---

## 12. Format action target

✅ **Resolved (contract-new-2)** — với điểm khác biệt quan trọng

Contract-new-2 dùng format **string** (KHÔNG phải object):
```json
{
  "action": "RESTART_DEPLOYMENT",
  "target": "deployment/cdo-sample-api",
  "params": { "namespace": "tenant-a" }
}
```

CDO đã đề xuất object format `{"namespace": "...", "deployment": "..."}` — **cần cập nhật executor code** để parse `target` string và `params.namespace` thay vì object. Pod-level targeting không được dùng (CDO đúng khi chỉ target Deployment level).

---

## Tổng kết trạng thái (2026-06-25, contract-new-2)

| # | Câu hỏi | Trạng thái |
|---|---|---|
| 1 | Mock API URL + auth | ✅ Resolved |
| 2 | Tenant ID | ✅ Resolved |
| 3 | Evidence acceptance | ⏳ Cần trainer confirm |
| 4 | pattern_type=deferred | ✅ Resolved |
| 5 | Confidence threshold | ✅ Resolved (CDO owns: 0.8) |
| 6 | suspected_fault_type enum | ⏳ Skip — sync AI team 2026-06-26 |
| 7 | Mock response coverage | ✅ Resolved (5/5 actions) |
| 8 | ROTATE_SECRET policy | ✅ Resolved |
| 9 | SQS ownership | ✅ Resolved |
| 10 | Topology registry format | ✅ Resolved (string format) |
| 11 | Fallback runbook | ✅ Resolved (CDO owns policy) |
| 12 | Action target format | ✅ Resolved (string, không phải object) |

**I/O schema đã chốt**: `/v1/decide` request bắt buộc `anomaly_context`; `/v1/verify` request bắt buộc `action_executed` ({action, target, status}); response bắt buộc `next_action` (DONE|RETRY|ROLLBACK|ESCALATE) và `regression_detected`. Schema được coi là **confirmed** từ contract-new-2.
