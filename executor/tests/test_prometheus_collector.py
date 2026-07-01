"""
Test PrometheusCollector — verify PromQL đúng schema podinfo + đổi đơn vị.

Verify:
  1. Mock mode trả 3 point đúng schema (đơn vị milliseconds cho latency_p95).
  2. _to_value() convert seconds → milliseconds cho latency_p95.
  3. _to_value() clamp [0.0, 1.0] cho error_rate.
  4. _to_value() clamp >= 0 cho throughput_rps (âm → 0).
  5. PromQL strings dùng `http_requests_total` (không phải `istio_*`).
  6. PromQL filter theo label `deployment` (relabel rule từ ServiceMonitor).

Convention: chạy `python tests/test_prometheus_collector.py` từ thư mục executor.
"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.prometheus_collector import PrometheusCollector


# ---------- 1. Mock mode trả 3 point đúng schema ----------

def test_mock_mode_returns_three_signals():
    """Mock mode trả đủ 3 signal name trong supported_signals."""
    c = PrometheusCollector()
    # Force mock mode regardless of env
    c._mock = True
    out = c.collect(
        tenant_id="6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
        namespace="tenant-a",
        deployment="cdo-sample-api",
        tenant_namespace="tenant-a",
    )
    assert len(out) == 3, f"Expected 3 points, got {len(out)}"
    signal_names = {p["signal_name"] for p in out}
    assert signal_names == {
        "service_error_rate",
        "service_latency_p95",
        "service_throughput_rps",
    }


def test_mock_point_has_correct_namespace_and_deployment():
    """Mỗi point phải có labels.namespace + labels.deployment đúng."""
    c = PrometheusCollector()
    c._mock = True
    out = c.collect(
        tenant_id="6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
        namespace="tenant-a",
        deployment="cdo-sample-api",
        tenant_namespace="tenant-a",
    )
    for p in out:
        assert p["labels"]["namespace"] == "tenant-a"
        assert p["labels"]["deployment"] == "cdo-sample-api"
        assert p["labels"]["source"] == "prometheus"


def test_mock_latency_p95_in_milliseconds():
    """
    Mock latency_p95 input = 0.85 SECONDS (raw) → _to_value() convert sang 850.0 ms.

    Verify theo chain end-to-end: mock value → _to_value() → milliseconds.
    """
    c = PrometheusCollector()
    c._mock = True
    out = c.collect(
        tenant_id="6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
        namespace="tenant-a",
        deployment="cdo-sample-api",
        tenant_namespace="tenant-a",
    )
    latency = next(p for p in out if p["signal_name"] == "service_latency_p95")
    assert latency["value"] == 850.0, f"Expected 850.0ms (after seconds→ms), got {latency['value']}"


# ---------- 2. _to_value ép đúng range & đổi đúng đơn vị ----------

def test_to_value_clamp_error_rate():
    """error_rate > 1.0 → clamp về 1.0; < 0 → 0.0."""
    assert PrometheusCollector._to_value("service_error_rate", 1.5) == 1.0
    assert PrometheusCollector._to_value("service_error_rate", -0.5) == 0.0
    assert PrometheusCollector._to_value("service_error_rate", 0.08) == 0.08


def test_to_value_latency_p95_seconds_to_milliseconds():
    """Histogram trả seconds → convert sang milliseconds (× 1000)."""
    # 0.85 seconds = 850 ms
    assert PrometheusCollector._to_value("service_latency_p95", 0.85) == 850.0
    # 1.234 seconds → 1234.0 ms (round 1 chữ số thập phân)
    assert PrometheusCollector._to_value("service_latency_p95", 1.234) == 1234.0
    # 0.005 seconds → 5.0 ms
    assert PrometheusCollector._to_value("service_latency_p95", 0.005) == 5.0


def test_to_value_throughput_non_negative():
    """throughput_rps không được âm; 0 OK."""
    assert PrometheusCollector._to_value("service_throughput_rps", 12.0) == 12.0
    assert PrometheusCollector._to_value("service_throughput_rps", -5.0) == 0.0
    assert PrometheusCollector._to_value("service_throughput_rps", 0.0) == 0.0


# ---------- 3. PromQL strings dùng đúng metric podinfo ----------

def test_promql_uses_http_requests_total():
    """
    PromQL PHẢI dùng `http_requests_total` (podinfo) — KHÔNG `istio_*`.

    Verify qua inspect source code: tìm PromQL strings trong collect().
    Pattern: nếu còn `istio_` → fail.
    """
    import inspect
    src = inspect.getsource(PrometheusCollector.collect)
    assert "istio_" not in src, \
        "FAIL: PrometheusCollector vẫn query istio_* (sai cho podinfo)"
    assert "http_requests_total" in src, \
        "FAIL: PrometheusCollector phải query http_requests_total (podinfo schema)"
    assert "http_request_duration_seconds_bucket" in src, \
        "FAIL: PrometheusCollector phải query histogram_seconds_bucket"


def test_promql_accepts_code_and_status_error_labels():
    """
    Podinfo emits `code`; ecommerce demo emits `status`.
    CDO must support both or service_error_rate will be silent for one workload.
    """
    import inspect
    src = inspect.getsource(PrometheusCollector.collect)
    assert 'code=~"5.."' in src
    assert 'status=~"5.."' in src


def test_promql_filters_by_deployment_label():
    """
    PromQL filter theo label `deployment` (relabel rule trong ServiceMonitor
    gán __meta_kubernetes_service_label_app → deployment).
    """
    import inspect
    src = inspect.getsource(PrometheusCollector.collect)
    # Đếm số lần xuất hiện filter deployment=
    matches = re.findall(r'deployment="\{deployment\}"', src)
    assert len(matches) >= 3, \
        f"Expected ≥ 3 PromQL queries filter by deployment, found {len(matches)}"


if __name__ == "__main__":
    import sys
    import io
    # Force UTF-8 để print tiếng Việt không crash trên Windows cp1252
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
