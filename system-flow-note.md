# System Flow Note - CDO-02 x AI

File này là note giải thích luồng hệ thống để team dễ hiểu. Đây không phải tài liệu Pack #1 chính.

## 1. Ý tưởng tổng quát

Trong TF3 Self-Heal Engine:

```text
AI = bộ não phân tích và đề xuất action
CDO = platform kiểm tra an toàn và thực thi action
Kubernetes = nơi workload thật đang chạy
Audit = bằng chứng ghi lại toàn bộ quá trình
```

CDO không để AI tự sửa Kubernetes trực tiếp. AI chỉ trả về `action_plan`. CDO sẽ kiểm tra action đó có an toàn không, rồi mới execute.

## 2. Luồng hệ thống đơn giản

```text
Alert xảy ra
-> CDO gom telemetry
-> CDO gọi AI /v1/detect
-> CDO gọi AI /v1/decide
-> AI trả action_plan
-> CDO chạy safety gate
-> CDO dry-run
-> CDO execute action trên Kubernetes
-> CDO gọi AI /v1/verify
-> CDO ghi audit
-> close incident hoặc rollback/escalate
```

## 3. Ví dụ cụ thể: service bị stuck

Giả sử service `api-service` trong namespace `tenant-a` bị latency cao.

### Bước 1 - Alert

Alert source hoặc scenario injector tạo incident:

```text
correlation_id = inc-001
tenant_id = tenant-a
namespace = tenant-a
service = api-service
problem = latency spike / service stuck
```

### Bước 2 - CDO gom telemetry

CDO gom dữ liệu để gửi cho AI:

```text
latency_p95
error_rate
memory_usage
app error logs
trace span errors
Kubernetes events
```

### Bước 3 - CDO gọi AI detect

CDO gọi:

```http
POST /v1/detect
```

Mục đích:

```text
Hỏi AI: "Đây có phải anomaly không?"
```

AI trả về:

```json
{
  "anomaly_detected": true,
  "severity": 0.85,
  "confidence": 0.91,
  "reasoning": "service_latency_p95 cao bất thường trong cửa sổ gần nhất",
  "correlation_id": "inc-001"
}
```

### Bước 4 - CDO gọi AI decide

Nếu AI xác nhận có anomaly, CDO gọi:

```http
POST /v1/decide
```

Mục đích:

```text
Hỏi AI: "Nên xử lý bằng action gì?"
```

AI trả về action plan:

```json
{
  "matched_runbook": "service_stuck",
  "pattern_type": "urgent",
  "action_plan": [
    {
      "step": 1,
      "action": "RESTART_DEPLOYMENT",
      "target": "deployment/api-service",
      "params": {
        "namespace": "tenant-a",
        "grace_period_seconds": 30
      }
    }
  ],
  "blast_radius_config": {
    "max_pod_impact_pct": 25,
    "circuit_breaker_error_rate": 0.2,
    "allowed_namespaces": ["tenant-a"]
  },
  "verify_policy": {
    "window_seconds": 180,
    "success_conditions": ["pod_ready == true", "service_latency_p95 < threshold"]
  }
}
```

### Bước 5 - CDO chạy safety gate

CDO không execute ngay. CDO kiểm tra:

```text
tenant_id có khớp namespace không?
action có nằm trong allow-list không?
blast-radius có vượt giới hạn không?
namespace có nằm trong allowed_namespaces không?
có verify_policy không?
Idempotency-Key có bị trùng không?
AI confidence có đủ không?
```

Nếu không đạt:

```text
deny action
ghi audit
escalate cho engineer
```

Nếu đạt:

```text
chạy dry-run
```

### Bước 6 - CDO dry-run

CDO thử action trước khi chạy thật:

```text
kubectl rollout restart deployment/api-service -n tenant-a --dry-run=server
```

Nếu dry-run fail:

```text
không execute thật
ghi audit
escalate
```

Nếu dry-run pass:

```text
execute thật
```

### Bước 7 - CDO execute trên Kubernetes

CDO gọi Kubernetes API để restart deployment:

```text
rollout restart deployment/api-service trong namespace tenant-a
```

Điểm quan trọng:

```text
AI không gọi Kubernetes trực tiếp.
CDO executor mới là nơi execute action.
```

### Bước 8 - CDO gọi AI verify

Sau action, CDO gom lại metrics:

```text
latency_p95 đã giảm chưa?
error_rate đã giảm chưa?
pod đã available chưa?
```

Sau đó CDO gọi:

```http
POST /v1/verify
```

Mục đích:

```text
Hỏi AI: "Action vừa rồi có xử lý được lỗi không?"
```

AI trả:

```json
{
  "success": true,
  "regression_detected": false,
  "next_action": "close_incident"
}
```

### Bước 9 - CDO ghi audit

CDO ghi lại toàn bộ quá trình:

```text
alert_received
telemetry_collected
detect_called
detect_response_received
decide_called
action_plan_received
safety_passed
dry_run_done
execute_done
verify_called
verify_done
incident_closed
```

Audit record phải có:

```text
correlation_id
tenant_id
namespace
action_type
decision
result
timestamp
```

## 4. Nếu có lỗi thì xử lý sao?

| Tình huống | CDO xử lý |
|---|---|
| AI timeout hoặc 503 | Không execute, escalate + audit |
| AI trả action thiếu verify_policy hoặc namespace không allowed | Deny action + audit |
| AI trả namespace sai tenant | Deny cross-tenant + audit |
| Dry-run fail | Không execute thật, escalate |
| Execute fail | Rollback nếu safe, nếu không escalate |
| Verify fail/regression | Rollback hoặc escalate |
| Audit write fail | Dừng action hoặc mark incident unsafe |

## 5. Tóm tắt vai trò

| Bên | Vai trò |
|---|---|
| AI team | Build AI engine, detect/decide/verify, trả action_plan |
| CDO team | Build platform, collect telemetry, safety gate, execute, verify integration, audit |
| Trainer/client | Chốt requirement, approve design, đưa curveball |

## 6. Câu cần nhớ khi present

```text
AI là decision service. CDO là execution control plane.
AI đề xuất action, nhưng CDO mới kiểm tra an toàn và thực thi trên Kubernetes.
```

