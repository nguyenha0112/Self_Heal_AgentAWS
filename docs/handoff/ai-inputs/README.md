# CDO to AI Handoff

Thư mục này chỉ chứa các payload mẫu mà phía CDO gửi cho AI theo contract đã chốt. Đây là phần bàn giao cho team AI để họ xác nhận parser, schema, field mapping và test input của họ.

## 6 JSON mẫu bàn giao

- `01_detect_request_oom_kill_tenant_a.json`
- `02_detect_request_latency_tenant_b.json`
- `03_decide_request_oom_kill_tenant_a.json`
- `04_decide_request_scale_capacity_tenant_b.json`
- `05_verify_request_memory_patch_tenant_a.json`
- `06_verify_request_restart_tenant_b.json`

## Header CDO gửi kèm khi gọi AI

CDO luôn gửi các header sau:

- `Content-Type: application/json`
- `X-Tenant-Id: 6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`
- `X-Correlation-Id: <uuid-v4>`
- `Idempotency-Key: <uuid-v4-or-deterministic-uuid>`
- `X-Dry-Run-Mode: true|false`

## Mục đích

- `detect_request`: input AI dùng để chạy `/v1/detect`
- `decide_request`: input AI dùng để chạy `/v1/decide`
- `verify_request`: input AI dùng để chạy `/v1/verify`

CDO không bàn giao logic execute hay rollback cho AI. AI chỉ cần xử lý đúng request/response contract ở 3 endpoint trên.
