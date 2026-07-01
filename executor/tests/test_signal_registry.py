"""
Test SignalRegistry — ánh xạ fault → signal + collector.

Convention: chạy `python tests/test_signal_registry.py` từ thư mục executor.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signal_registry import (
    FAULT_TO_SIGNALS,
    K8S_WAITING_TO_FAULT,
    SignalRegistry,
    default_registry,
)
from collectors import CollectorRegistry


# ---------- 1. Fault → signal mapping ----------

def test_oom_kill_resolves_to_memory_signals():
    """OOM_KILL phải map sang pod_oom_event + container_resource_usage."""
    reg = SignalRegistry()
    req = reg.resolve("OOM_KILL")
    assert req.fault_type == "OOM_KILL"
    assert "pod_oom_event" in req.signals
    assert "container_resource_usage" in req.signals


def test_secret_expiry_resolves_to_correct_signal():
    """CERT_EXPIRY → secret_expiry_warning."""
    reg = SignalRegistry()
    req = reg.resolve("CERT_EXPIRY")
    assert "secret_expiry_warning" in req.signals


def test_unknown_fault_returns_empty_signals():
    """UNKNOWN fault → signals rỗng → caller phải dùng collect_all()."""
    reg = SignalRegistry()
    req = reg.resolve("UNKNOWN")
    assert req.signals == []


def test_k8s_waiting_reason_maps_to_fault():
    """K8s waiting_reason → fault_type qua bảng K8S_WAITING_TO_FAULT."""
    assert K8S_WAITING_TO_FAULT["OOMKilled"] == "OOM_KILL"
    assert K8S_WAITING_TO_FAULT["CrashLoopBackOff"] == "CRASH_LOOP"
    assert K8S_WAITING_TO_FAULT["ImagePullBackOff"] == "BAD_DEPLOY"


def test_resolve_from_k8s_reason_chain():
    """K8s reason → fault → signals phải trả đúng signal mong đợi."""
    reg = SignalRegistry()
    req = reg.resolve_from_k8s_reason("OOMKilled")
    assert req.fault_type == "OOM_KILL"
    assert "pod_oom_event" in req.signals


# ---------- 2. Registry.collect_for_signal ----------

class _MockCollector:
    name = "mock"
    supported_signals = ("service_error_rate", "queue_backlog")

    def collect(self, **kw):
        return [{
            "ts": "2026-06-30T00:00:00.000Z",
            "tenant_id": "6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
            "service": kw.get("deployment", ""),
            "signal_name": "service_error_rate",
            "value": 0.05,
            "labels": {"system": "TEST", "namespace": kw.get("namespace", "")},
        }]


def test_collect_for_signal_dispatches_to_owner():
    """collect_for_signal gọi đúng collector sở hữu signal đó."""
    cr = CollectorRegistry([_MockCollector()])
    reg = SignalRegistry(collector_registry=cr)
    points = reg.collect_for_signal(
        "service_error_rate",
        tenant_id="6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
        namespace="tenant-a",
        deployment="checkout-svc",
        tenant_namespace="tenant-a",
    )
    assert len(points) == 1
    assert points[0]["signal_name"] == "service_error_rate"


def test_collect_for_signal_returns_empty_if_no_collector():
    """Signal không có collector → trả [] (không raise)."""
    cr = CollectorRegistry([_MockCollector()])
    reg = SignalRegistry(collector_registry=cr)
    points = reg.collect_for_signal(
        "secret_expiry_warning",
        tenant_id="6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
        namespace="tenant-a",
        deployment="checkout-svc",
        tenant_namespace="tenant-a",
    )
    assert points == []


def test_resolve_lists_collector_names():
    """resolve() phải liệt kê collector sẽ được gọi."""
    cr = CollectorRegistry([_MockCollector()])
    reg = SignalRegistry(collector_registry=cr)
    req = reg.resolve("ERROR_RATE_HIGH")
    assert "mock" in req.collector_names


# ---------- 3. Default registry (integration smoke test) ----------

def test_default_registry_covers_all_12_signals():
    """
    default_registry() phải cover đủ 12 signal trong telemetry-contract §3.

    Signal đếm:
      1. service_error_rate          (PrometheusCollector)
      2. service_latency_p95         (PrometheusCollector)
      3. service_throughput_rps      (PrometheusCollector)
      4. application_log_event       (LogCollector)
      5. distributed_trace_error_event(LogCollector)
      6. container_resource_usage    (K8sMetricsCollector)
      7. queue_backlog               (ExternalCollector)
      8. db_connection_pool_saturation(ExternalCollector)
      9. secret_expiry_warning       (ExternalCollector)

    Còn lại 3 signal do K8sWatcher (watcher.py) cover:
      10. pod_oom_event
      11. container_restart_count
      12. service_unhealthy
    → Tổng 12.
    """
    reg = default_registry()
    supported = reg._collectors.supported_signals  # type: ignore[attr-defined]
    expected_from_registry = {
        "service_error_rate", "service_latency_p95", "service_throughput_rps",
        "application_log_event", "distributed_trace_error_event",
        "container_resource_usage",
        "queue_backlog", "db_connection_pool_saturation", "secret_expiry_warning",
    }
    assert expected_from_registry.issubset(supported), \
        f"Missing signals: {expected_from_registry - supported}"


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    failed = 0
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(0 if failed == 0 else 1)