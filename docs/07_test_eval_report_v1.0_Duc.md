# Test & Eval Report - Task Force 3 Self-Heal Engine - CDO-02

**Doc owner:** CDO-02  
**Trạng thái:** Draft cho W12 Pack #2 execution  
**Cập nhật lần cuối:** 2026-06-25 (sync AI commit 86b32e7)  

## 1. Mục tiêu tài liệu

Tài liệu này mô tả test cases, phạm vi test và evidence cần thu cho platform CDO-02 của TF3 Self-Heal Engine. Mục tiêu không chỉ là chứng minh một happy path chạy được, mà là chứng minh CDO executor có thể tự động xử lý known patterns trong giới hạn an toàn.

Luồng test chính:

```text
alert -> telemetry -> AI detect -> AI decide -> CDO safety gate -> dry-run -> execute/mock execute -> verify -> audit -> close/rollback/escalate
```

Boundary dùng cho toàn bộ test:

- AI Engine là decision service qua `/v1/detect`, `/v1/decide`, `/v1/verify`.
- CDO executor là execution boundary duy nhất trước khi có Kubernetes mutation.
- Mọi action phải qua safety gate, dry-run, blast-radius, verify, rollback/circuit breaker và audit.
- Multi-tenant isolation giữa `tenant-a` và `tenant-b` là hard gate. Nếu có cross-tenant action được execute, toàn bộ test suite fail.

## 2. Test Coverage

| Test type | Tool / Method | Phạm vi | Trạng thái |
|---|---|---|---|
| Contract test | JSON schema + signed AI contract | Validate request/response cho `/v1/detect`, `/v1/decide`, `/v1/verify` | Planned |
| Safety unit test | pytest hoặc module test tương đương | Validate allow-list, tenant match, blast-radius, local rollback/runbook path, `verify_policy`, idempotency | Planned |
| Integration test | Mock AI endpoint + CDO executor | Alert payload -> AI decision -> safety decision -> audit record | Planned |
| Kubernetes action test | EKS/Kubernetes sandbox + server-side dry-run | Restart deployment, scale worker, deny unsafe namespace/action | Planned |
| E2E scenario test | Scenario injector + Prometheus/Alertmanager hoặc offline RE2/RE3 preprocessor | >= 10 injected scenarios trong >= 4h simulation window | Planned |
| Load test | k6/Locust hoặc scenario replay runner | Sustained telemetry/API flow và executor queue behavior | Planned |
| Security test | Manual abuse cases + RBAC checks | Cross-tenant deny, secret/log exposure, IAM/RBAC least privilege | Planned |
| Audit evidence test | S3 Object Lock hoặc append-only audit target + CloudWatch logs | Query toàn bộ events theo `correlation_id`, retention target >= 90 days | Planned |

## 3. Acceptance Criteria

| Requirement | Target | Evidence source | Trạng thái |
|---|---:|---|---|
| Scenario count | >= 10 injected scenarios | Scenario run log | Pending W12 evidence |
| Simulation window | >= 4 hours | Start/end timestamps trong audit/logs | Pending W12 evidence |
| Auto-resolve rate | >= 60% | Scenario summary table | Pending W12 evidence |
| Unsafe action count | 0 | Safety/audit records | Pending W12 evidence |
| Multi-tenant isolation | 100% deny cho cross-tenant attempts | RBAC + safety tests | Pending W12 evidence |
| Audit trail | 100% scenarios có trace theo `correlation_id` | Audit query output | Pending W12 evidence |
| Safety checkpoints | 5/5 enforced cho mutating actions | Safety gate test output | Pending W12 evidence |

## 4. SLO Evidence

Các SLO dưới đây là target cho W12 Pack #2. Cột measured chỉ được điền sau khi chạy test thật, không điền số giả định.

| SLO | Target | Measured | Window | Pass/Fail |
|---|---:|---:|---|---|
| CDO executor availability trong simulation | >= 99.5% | TBD | >= 4h scenario window | TBD |
| AI API call p99 do CDO observe | detect < 300ms; decide < 3000ms (LLM) / < 500ms (fallback); verify < 500ms | TBD | Scenario run | TBD |
| End-to-end auto-heal latency | < 5 min cho safe restart/scale cases | TBD | Successful auto-resolve cases | TBD |
| Audit write coverage | 100% incidents | TBD | Scenario run | TBD |
| Unsafe action rate | 0% | TBD | Scenario run | TBD |
| Tenant onboarding smoke test | < 30 min cho 2 tenants | TBD | `tenant-a`, `tenant-b` setup | TBD |
| Rate limit compliance | detect <= 100 RPS; decide/verify <= 10 RPS per tenant | TBD | Scenario run | TBD |

### 4.1 SLO Breach Analysis Template

Nếu có SLO miss sau khi chạy test, điền bảng này để giải thích root cause và fix.

| SLO missed | Hành vi quan sát được | Root cause | Fix attempted | Final status |
|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD |

## 5. Test Case Matrix

### 5.1 Known Pattern Scenarios

| ID | Scenario | Tenant | Signal source | Expected AI decision | Expected CDO action | Expected result |
|---|---|---|---|---|---|---|
| TC-01 | Service stuck / latency spike | `tenant-a` | `service_latency_p95` | `service_stuck` | `RESTART_DEPLOYMENT` sau khi safety pass | Auto-resolved |
| TC-02 | Service stuck / latency spike | `tenant-b` | `service_latency_p95` | `service_stuck` | `RESTART_DEPLOYMENT` sau khi safety pass | Auto-resolved |
| TC-03 | Error rate spike | `tenant-a` | `service_error_rate`, app logs | `error_rate_spike` | Restart nếu confidence/safety pass, nếu không thì escalate | Auto-resolved hoặc escalated safely |
| TC-04 | Memory pressure / OOM prevention | `tenant-a` | `container_resource_usage` | `memory_pressure` | `PATCH_MEMORY_LIMIT` chỉ khi có verify_policy và local rollback/runbook path | Auto-resolved hoặc denied safely |
| TC-05 | Queue/backpressure | `tenant-b` | queue depth hoặc synthetic backlog metric | `queue_backlog` | `SCALE_REPLICAS` trong giới hạn blast-radius | Auto-resolved |
| TC-06 | Cert/secret/config issue | `tenant-a` | app logs / synthetic alert | `config_issue` | `ROTATE_SECRET` bị deny nếu chưa được allow rõ | Escalated safely |

### 5.2 Safety And Failure Scenarios

| ID | Scenario | Injected fault | Expected CDO decision | Pass condition |
|---|---|---|---|---|
| TC-07 | Cross-tenant target | Incident tenant là `tenant-a`, AI action target `tenant-b` | Deny action | Không có Kubernetes mutation, audit reason `denied_cross_tenant` |
| TC-08 | Action ngoài allow-list | AI trả `DELETE_NAMESPACE` | Deny action | Không có Kubernetes mutation, audit reason `denied_action_not_allowed` |
| TC-09 | Thiếu local rollback/runbook path | Mutating action không có fallback path cục bộ | Deny action | Audit ghi `missing_rollback_path` |
| TC-10 | Thiếu `verify_policy` | Mutating action không có `verify_policy.window_seconds` | Deny action | Audit ghi `missing_verify_policy` |
| TC-11 | Duplicate idempotency key | Retry cùng action với cùng `Idempotency-Key` | Deny duplicate execute | Chỉ có 1 execute event cho key đó |
| TC-12 | AI timeout/503 | `/v1/decide` timeout hoặc trả 503 | Escalate, không execute | Audit ghi `ai_unavailable_escalated` |
| TC-13 | Dry-run failure | Kubernetes server-side dry-run fail | Deny execute | Không có real action sau dry-run fail |
| TC-14 | Verify regression | Post-action metrics xấu hơn | Rollback hoặc escalate | Audit có rollback/escalation event |
| TC-15 | Circuit breaker | Quá nhiều action fail trong thời gian ngắn | Stop automation | Các action tiếp theo bị deny tới khi breaker reset |
| TC-16 | `pattern_type: deferred` routing | AI trả `pattern_type: "deferred"` (e.g. SCALE_REPLICAS) | CDO tạo Git commit/PR, **không** gọi K8s API trực tiếp | Không có K8s mutation, có Git commit/PR evidence, audit ghi `deferred_gitops_path` |
| TC-17 | `cost_cap_exceeded: true` handling | AI `/v1/decide` trả `cost_cap_exceeded: true` | CDO log warning + notify, vẫn execute action plan theo safety gate | Audit ghi `cost_cap_exceeded_warning`, action executed bình thường |

## 6. Detailed Test Cases

### TC-01 - Service Stuck Auto-Restart

**Goal:** Chứng minh CDO có thể auto-resolve một latency spike an toàn bằng cách restart đúng một deployment trong đúng namespace.

**Preconditions:**

- Namespace `tenant-a` đã tồn tại.
- Target deployment có label `tenant_id=tenant-a`.
- AI mock/real endpoint có thể trả `RESTART_DEPLOYMENT`.
- Audit sink đang available.

**Steps:**

1. Inject alert với `correlation_id=tc-01-*`, tenant `tenant-a`, namespace `tenant-a`.
2. Cung cấp telemetry cho thấy `service_latency_p95` cao bất thường.
3. CDO gọi `/v1/detect` và `/v1/decide`.
4. AI trả `RESTART_DEPLOYMENT` cho một deployment, có `verify_policy`; CDO có local rollback/runbook path.
5. Safety gate validate tenant, allow-list, blast-radius, rollback/runbook path, `verify_policy` và idempotency.
6. CDO chạy server-side dry-run.
7. CDO execute hoặc mock-execute restart.
8. CDO gọi `/v1/verify`.
9. CDO ghi full audit trail.

**Expected result:** Incident được close dưới trạng thái auto-resolved. Audit có `safety_passed`, `dry_run_done`, `execute_done`, `verify_done`, `incident_closed`.

### TC-07 - Cross-Tenant Action Deny

**Goal:** Chứng minh CDO chặn tenant isolation violation ngay cả khi AI trả sai target.

**Steps:**

1. Inject incident với `tenant_id=tenant-a`.
2. Mock response của AI `/v1/decide` target namespace `tenant-b`.
3. Chạy CDO safety gate.

**Expected result:** CDO deny trước dry-run/execute. Audit có `safety_denied` với reason `denied_cross_tenant`. Kubernetes mutation count bằng 0.

### TC-12 - AI Timeout Escalation

**Goal:** Chứng minh platform fail-safe khi AI unavailable.

**Steps:**

1. Inject một valid incident.
2. Force `/v1/decide` timeout hoặc HTTP 503.
3. Quan sát fallback behavior của CDO.

**Expected result:** CDO không tự execute static action theo default. Incident được escalate kèm context bundle và audit reason `ai_unavailable_escalated`.

### TC-14 - Verify Regression Rollback/Escalation

**Goal:** Chứng minh workflow không đánh dấu remediation fail thành success.

**Steps:**

1. Inject một safe action scenario.
2. Trả kết quả dry-run/execute success.
3. Cung cấp post-action telemetry cho thấy regression.
4. CDO gọi `/v1/verify`.

**Expected result:** CDO chạy rollback nếu local rollback/runbook path an toàn; nếu không thì escalate. Audit có `verify_regression` và `rollback_done` hoặc `escalated`.

## 7. Scenario Simulation Plan

W12 evidence run phải inject ít nhất 10 scenarios trong tối thiểu 4 giờ.

| Phase | Duration | Activity | Evidence |
|---|---:|---|---|
| Warm-up | 15 min | Verify namespaces, AI endpoint, audit sink, telemetry path | Readiness log |
| Baseline | 30 min | Chạy workload không inject fault | Baseline metrics |
| Scenario wave 1 | 90 min | TC-01 tới TC-06 cho known pattern cases | Scenario logs + audit |
| Scenario wave 2 | 90 min | TC-07 tới TC-15 cho safety/failure cases | Safety deny/escalation audit |
| Cooldown | 15 min | Verify không còn stuck incident, tổng hợp kết quả | Final report |

Các metric tối thiểu cần thu:

| Metric | Formula |
|---|---|
| Auto-resolve rate | `auto_resolved_count / total_injected_scenarios` |
| Unsafe action count | Số real Kubernetes mutations vi phạm tenant/action/blast-radius rules |
| Audit coverage | `scenarios_with_complete_audit / total_injected_scenarios` |
| Escalation quality | Escalated incidents có logs, metrics, deploy history và attempted actions đi kèm |

## 8. Load Test Results

### 8.1 Test Setup

Planned load profile:

- Ramp-up: 0 -> 100 simulated alert/API events mỗi phút trong 5 phút.
- Sustained: 100 events mỗi phút trong 10 phút.
- Tenants simulated: namespaces `tenant-a`, `tenant-b`; request header uses CDO-02 tenant UUID `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c` pending AI confirmation.
- Tool: k6, Locust hoặc scenario replay runner.

### 8.2 Results

| Metric | Target | Achieved | Pass/Fail |
|---|---:|---:|---|
| Events sustained | 100/min | TBD | TBD |
| CDO executor p99 workflow latency | < 5 min cho safe auto-resolve | TBD | TBD |
| AI call error rate observed by CDO | < 1%, không tính forced failure tests | TBD | TBD |
| Audit write success | 100% | TBD | TBD |
| Queue backlog recovery | Backlog drain sau sustained window | TBD | TBD |

### 8.3 Bottleneck Identified

TBD sau khi chạy test. Các bottleneck cần theo dõi:

- AI endpoint rate limit hoặc p99 latency.
- Telemetry queue depth.
- Kubernetes API dry-run latency.
- Audit sink write latency.
- Executor concurrency và idempotency lock contention.

## 9. Security Test

### 9.1 Penetration Touch Points

| Check | Method | Expected result | Status |
|---|---|---|---|
| API auth bypass attempt | Gọi AI/CDO endpoint không có required auth/header | 401/403 hoặc request bị reject | Pending |
| Cross-tenant data/action leak | Dùng incident `tenant-a` để target namespace `tenant-b` | Safety deny + no mutation | Pending |
| Action allow-list bypass | Cho AI trả unsupported action | Safety deny | Pending |
| IAM/K8s privilege escalation | Thử delete namespace hoặc cluster-wide mutation | RBAC deny | Pending |
| Secret exposure via logs | Inspect logs tìm token/SigV4/kube token | Không log sensitive value | Pending |

### 9.2 Vulnerability Scan

| Target | Tool | Acceptance |
|---|---|---|
| Container image | Trivy hoặc Snyk | 0 critical findings; high findings phải có mitigation |
| Terraform/IaC | tfsec/checkov nếu available | Critical misconfigurations được fix hoặc documented |
| Kubernetes manifests/RBAC | kube-score/polaris/manual review | Executor không có `cluster-admin` |

Report target:

```text
security/scan-results.json
```

## 10. Multi-Tenant Isolation Test

Toàn bộ test trong section này phải pass. Nếu có bất kỳ cross-tenant mutation nào execute thành công, đây là SEV1 failure cho capstone.

| Test | Method | Expected result |
|---|---|---|
| Tenant A đọc action context của Tenant B | Inject A token/header nhưng request B target | Request bị deny hoặc context bị omit |
| Tenant A action target Tenant B namespace | Mock AI action target namespace `tenant-b` | Safety deny trước dry-run |
| Tenant A ServiceAccount mutate Tenant B workload | Thử Kubernetes patch bằng A-scoped identity | RBAC deny |
| Cross-tenant queue contamination | Queue message có `tenant_id` và namespace không khớp | Message bị reject hoặc safety denied |
| Audit query by tenant | Query audit cho `tenant-a` | Không expose payload content của `tenant-b` |

## 11. Yêu Cầu Audit Evidence

Mọi scenario phải query được bằng `correlation_id`. Audit trail tối thiểu cần có:

```text
alert_received
telemetry_collected
detect_called
detect_response_received
decide_called
action_plan_received
idempotency_lock_acquired or idempotency_duplicate_denied
safety_passed or safety_denied
dry_run_done or dry_run_failed
execute_done or execute_skipped
verify_called
verify_done
rollback_done or escalated or incident_closed
```

Audit fields tối thiểu:

| Field | Required | Notes |
|---|---|---|
| `timestamp` | Yes | RFC3339 UTC |
| `correlation_id` | Yes | Stable trong toàn workflow |
| `tenant_id` | Yes | Phải khớp namespace mapping |
| `namespace` | Yes | Kubernetes target namespace |
| `action_type` | Yes cho decision/action events | Lấy từ allow-list |
| `decision` | Yes | execute, deny, escalate, rollback, close |
| `result` | Yes | success, failure, denied, skipped |
| `reason` | Yes cho deny/failure | Machine-readable reason |
| `idempotency_key` | Yes cho mutating workflow | Dùng để chống duplicate execution |

## 12. Failure Analysis

Điền sau khi chạy test.

| # | Failure | Root cause | Fix | Time to fix | Final status |
|---|---|---|---|---:|---|
| TBD | TBD | TBD | TBD | TBD | TBD |

## 13. Test Gaps Acknowledged

Các gap đã biết trước W12 execution:

- Real production traffic nằm ngoài scope; test dùng sandbox workload và/hoặc RE2/RE3 offline simulation.
- Cross-region audit replication nằm ngoài scope.
- Full long-term Prometheus retention với Thanos/Cortex/Mimir nằm ngoài scope.
- Real PagerDuty/OpsGenie integration nằm ngoài scope; Slack/mock pager escalation là đủ cho capstone.
- Nếu AWS/EKS quota hoặc account access chặn full deployment, evidence phải ghi rõ test nào chạy trên Kubernetes sandbox và test nào chạy ở offline/mock mode.

## 14. Tóm Tắt Kết Quả Cuối

Điền bảng này sau W12 evidence run.

| Summary metric | Target | Actual | Pass/Fail |
|---|---:|---:|---|
| Total scenarios injected | >= 10 | TBD | TBD |
| Scenario window | >= 4h | TBD | TBD |
| Auto-resolve rate | >= 60% | TBD | TBD |
| Unsafe actions | 0 | TBD | TBD |
| Cross-tenant leaks | 0 | TBD | TBD |
| Complete audit coverage | 100% | TBD | TBD |
| Critical security findings | 0 | TBD | TBD |

## Tài Liệu Liên Quan

- [`01_requirements_analysis.md`](01_requirements_analysis.md)
- [`02_infra_design.md`](02_infra_design.md)
- [`03_security_design.md`](03_security_design.md)
- [`08_adrs.md`](08_adrs.md)
- [`../system-flow-note.md`](../system-flow-note.md)
- [`docs_ObservabilityStack/Prometheus.md`](docs_ObservabilityStack/Prometheus.md)
