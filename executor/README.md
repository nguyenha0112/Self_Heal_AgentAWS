# CDO Self-Heal Executor — Skeleton

Trái tim runtime của CDO-02: vòng `detect → pre-decide gate → decide → safety gate → snapshot → execute → verify → audit`. Align với **contract-new-4**.

> Trạng thái: **skeleton chạy được**. Main loop + Pre-Decide Gate + Safety Gate + AI client (error/retry policy) + audit đã hoàn chỉnh. Phần K8s/AWS/Deferred là stub có TODO(W12).

## Cấu trúc module

| File | Vai trò | Mức |
|---|---|---|
| `main.py` | **Orchestration loop** + CLI chạy 1 scenario + `--watch` mode | ✅ đầy đủ |
| `pre_decide_gate.py` | 7-condition gate sau detect (confidence/severity/flapping/maintenance) | ✅ đầy đủ |
| `safety_gate.py` | **Safety gate** (tenant match, allow-list, blast-radius, routing, verify_policy) | ✅ đầy đủ |
| `ai_client.py` | HTTP client 3 endpoint + error policy §4 (400/401/403/409/429/500×2/503) | ✅ đầy đủ |
| `models.py` | Dataclass I/O schema (Detect/Decide/Verify) | ✅ đầy đủ |
| `errors.py` | Exception map theo HTTP code | ✅ đầy đủ |
| `config.py` | Config env-driven (tenant, endpoint, caps, namespaces, collector sources) | ✅ đầy đủ |
| `signal_registry.py` | **SignalRegistry** — ánh xạ `fault_type → signals → collector` cho 12 signal | ✅ đầy đủ |
| `collectors/__init__.py` | `SignalCollector` interface + `CollectorRegistry` (Strategy pattern) | ✅ đầy đủ |
| `collectors/prometheus_collector.py` | Scrape 3 service signal (`error_rate`, `latency_p95`, `throughput_rps`) | ✅ mock + real |
| `collectors/k8s_metrics_collector.py` | Scrape `container_resource_usage` từ K8s Metrics Server | ✅ mock + real |
| `collectors/log_collector.py` | Scrape `application_log_event` + `distributed_trace_error_event` | ✅ mock + real |
| `collectors/external_collector.py` | Scrape `queue_backlog` (SQS) + `db_connection_pool_saturation` + `secret_expiry_warning` | ✅ mock + real |
| `idempotency.py` | DynamoDB conditional write (decide-only) | 🟡 logic xong, cần boto3+table |
| `audit.py` | Audit theo correlation_id → S3 Object Lock | 🟡 stdout xong, cần boto3+bucket |
| `k8s_client.py` | Wrapper K8s (get state, restart/patch/rollout-undo + dry-run, **get_pod_metrics**) | 🟡 stub, cần kubernetes lib |
| `watcher.py` | K8s pod status poll → 4 signal (`oom_event`, `restart_count`, `unhealthy`, `crash`) | ✅ đầy đủ |
| `snapshot.py` | CDO tự capture rollback snapshot trước execute | 🟡 urgent xong, deferred=git stub |
| `executors/urgent.py` | Path B — K8s API trực tiếp (dry-run rồi execute) | 🟡 wiring xong, call=stub |
| `executors/deferred.py` | Path A — Git commit → ArgoCD sync | 🔴 stub (cân nhắc designed-only) |
| `mock_ai_server.py` | Mock AI endpoint đúng schema — integrate trước khi có image AI | ✅ đầy đủ |

## Signal Coverage (12 signal theo telemetry-contract §3)

| # | Signal | Collector | Nguồn | Trigger fault |
|---|---|---|---|---|
| 1 | `service_error_rate` | `PrometheusCollector` | PromQL `http_requests_total{code=~"5.."}` | `ERROR_RATE_HIGH` |
| 2 | `service_latency_p95` | `PrometheusCollector` | PromQL `histogram_quantile(0.95, ...)` | `LATENCY_SPIKE`, `SERVICE_STUCK` |
| 3 | `service_throughput_rps` | `PrometheusCollector` | PromQL `rate(http_requests_total[1m])` | `LATENCY_SPIKE`, `SERVICE_STUCK` |
| 4 | `application_log_event` | `LogCollector` | CloudWatch Logs Insights / OTel | `CRASH_LOOP`, `ERROR_RATE_HIGH`, `BAD_DEPLOY` |
| 5 | `distributed_trace_error_event` | `LogCollector` | OTel trace pipeline / CW Logs | `ERROR_RATE_HIGH` |
| 6 | `container_resource_usage` | `K8sMetricsCollector` | K8s Metrics Server (`metrics.k8s.io`) | `OOM_KILL`, `MEMORY_PRESSURE` |
| 7 | `pod_oom_event` | K8sWatcher (`watcher.py`) | K8s pod `state.waiting.reason` | `OOM_KILL` |
| 8 | `container_restart_count` | K8sWatcher | K8s pod `restart_count` | `CRASH_LOOP` |
| 9 | `service_unhealthy` | K8sWatcher | K8s ImagePull / probe failure | `BAD_DEPLOY`, `CERT_EXPIRY` |
| 10 | `queue_backlog` | `ExternalCollector` | SQS `GetQueueAttributes` | `QUEUE_BACKLOG` |
| 11 | `db_connection_pool_saturation` | `ExternalCollector` | HikariCP PromQL | `DB_POOL_SATURATION` |
| 12 | `secret_expiry_warning` | `ExternalCollector` | Secrets Manager `DescribeSecret` | `CERT_EXPIRY` |

| `tests/test_signal_registry.py` | 9 test SignalRegistry (fault → signal mapping) | ✅ đầy đủ |
| `tests/test_prometheus_collector.py` | 8 test PrometheusCollector (PromQL, _to_value, đổi đơn vị) | ✅ đầy đủ |
| `tests/test_chain_integration.py` | 5 test chain podinfo → Prometheus → Collector (manifest + label) | ✅ đầy đủ |

Khi watcher phát hiện fault (vd `OOMKilled` → fault_type=`OOM_KILL`), `Executor.handle_incident()` gọi `SignalRegistry.collect_for_fault()`:

```python
# main.py:_enrich_with_signals()
req = self.signals.resolve(fault_type)
# req.signals = ["pod_oom_event", "container_resource_usage", "container_restart_count"]
# req.collector_names = ["k8s_metrics"]

# Với mỗi signal, scrape từ collector tương ứng
for sig in req.signals:
    extra_points.extend(self.signals.collect_for_signal(
        signal_name=sig, tenant_id=..., namespace=..., deployment=...))
```

Bảng `FAULT_TO_SIGNALS` trong `signal_registry.py` định nghĩa fault → signals.
Thêm fault mới = thêm 1 entry vào dict, không cần đổi code khác.

### Mock mode cho Day-1

Mỗi collector có `_mock_*` fallback khi `CDO_K8S_MOCK=true` hoặc thiếu lib — trả về data đúng schema để executor chạy hết loop ở offline mode.

## Sandbox end-to-end (Prometheus thật từ podinfo)

Chain đầy đủ chạy trên EKS cluster (không mock Prometheus/K8s):

```bash
# 1. Deploy Prometheus stack (Terraform hoặc Helm)
kubectl apply -f manifests/observability/servicemonitor-sample-apps.yaml

# 2. Deploy sample workload (podinfo)
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml

# 3. Apply PrometheusRules (3 service signal alerts)
kubectl apply -f manifests/observability/prometheus-rule-service-signals.yaml

# 4. Verify Prometheus scrape được podinfo
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Mở http://127.0.0.1:9090/targets → serviceMonitor cdo-sample-apps/cdo-sample
# phải có state=UP sau ~30s.

# 5. Generate traffic để scrape có data
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 &
for i in 1 2 3 4 5; do curl http://127.0.0.1:9898/healthz; curl http://127.0.0.1:9898/readyz; done

# 6. Verify PromQL trả data đúng
curl http://127.0.0.1:9090/api/v1/query?query='http_requests_total{deployment="cdo-sample-api"}'
```

### PromQL khớp podinfo (KHÔNG Istio)

| Signal | PromQL (đã verify) |
|---|---|
| `service_error_rate` | `sum(rate(http_requests_total{deployment="<name>",code=~"5.."}[1m])) / sum(rate(http_requests_total{deployment="<name>"}[1m]))` |
| `service_latency_p95` | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{deployment="<name>"}[1m])) by (le))` ← seconds, convert sang ms trong `_to_value()` |
| `service_throughput_rps` | `sum(rate(http_requests_total{deployment="<name>"}[1m]))` |

### File liên quan

- `manifests/observability/servicemonitor-sample-apps.yaml` — scrape podinfo `:9797/metrics` với `release=kube-prometheus-stack` label, relabel rule gán `__meta_kubernetes_service_label_app` → `deployment`.
- `manifests/workloads/tenant-{a,b}-sample-app.yaml` — đã có thêm label `tier=cdo-sample` để match ServiceMonitor selector.
- `executor/collectors/prometheus_collector.py` — query theo schema podinfo, đổi seconds → milliseconds cho `service_latency_p95`.

## Day-1 smoke test (offline, không cần cluster/AWS)

```bash
cd executor
pip install -r requirements.txt

# terminal 1: mock AI
python mock_ai_server.py

# terminal 2: chạy 1 scenario qua mock, K8s mock
CDO_K8S_MOCK=true AI_BASE_URL=http://127.0.0.1:8080 \
  python main.py scenarios/tc01_service_stuck.json
# → OUTCOME: auto_resolved, audit trail đầy đủ ra stdout

# safety gate unit test (8 case deny/allow)
python tests/test_safety_gate.py
```

## Lộ trình W12 (theo độ ưu tiên)

1. **MUST** — `k8s_client.py`: implement restart + patch_memory (server-side dry-run `dry_run="All"`). Bỏ comment `kubernetes` trong requirements. → TC-01..04 chạy thật trên EKS.
2. **MUST** — `audit.py` + `idempotency.py`: bỏ comment `boto3`, set `CDO_AUDIT_BUCKET` + `CDO_IDEMPOTENCY_TABLE` (Terraform module `audit/` đã tạo sẵn).
3. **MUST** — inject script + chạy ≥10 scenario / ≥4h → auto-resolve rate.
4. **SHOULD** — `executors/deferred.py`: Git→ArgoCD (TC-05/06/16). **Nếu thiếu thời gian → hạ queue/secret về designed-only.**
5. **SHOULD** — `_escalate`: Slack/mock pager + escalation_bundle.

## Lưu ý contract cần chốt trước W12 T1
- **SA namespace**: `CDO_EXECUTOR_NS` đang default `self-heal-system` theo contract §3.D. Nếu giữ `platform` phải có agreement văn bản với AI team.
- Không commit secret thật; không dùng static AWS key trong pod (IRSA).
