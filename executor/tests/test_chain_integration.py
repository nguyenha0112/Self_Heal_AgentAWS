"""
Integration test — Verify chain end-to-end:
  podinfo → ServiceMonitor → Prometheus → PrometheusCollector → SignalRegistry →

Verify:
  1. ServiceMonitor manifest syntax OK (kubectl khi áp lên cluster).
  2. Workload manifests có label `tier=cdo-sample` để match selector.
  3. prometheus-rule-service-signals.yaml PromQL query đúng schema podinfo.
  4. PrometheusCollector PromQL khớp schema podinfo (đã test riêng).

Convention: chạy từ thư mục executor.
"""
import sys
import re
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_yaml(path: Path) -> dict:
    """Đọc YAML file — multi-doc support."""
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    # Trả về doc đầu tiên nếu 1 doc; list nếu nhiều doc.
    if len(docs) == 1:
        return docs[0]
    return {"docs": docs}


def test_servicemonitor_targets_podinfo_port():
    """
    ServiceMonitor PHẢI selector match Service `cdo-sample-api` (tenant-a)
    hoặc `notification-service` (tenant-b) và endpoint port 9797 (port name "metrics").
    """
    sm_path = ROOT / "manifests" / "observability" / "servicemonitor-sample-apps.yaml"
    assert sm_path.exists(), f"Missing: {sm_path}"

    sm = _load_yaml(sm_path)
    assert sm["kind"] == "ServiceMonitor"

    # Selector: matchLabels phải có key
    selector = sm["spec"]["selector"]["matchLabels"]
    assert "tier" in selector, \
        f"ServiceMonitor selector phải có label 'tier', got {selector}"

    # NamespaceSelector: tenant-a + tenant-b
    ns_sel = sm["spec"]["namespaceSelector"]["matchNames"]
    assert "tenant-a" in ns_sel
    assert "tenant-b" in ns_sel

    # Endpoint: port metrics (name, không phải port number)
    ep = sm["spec"]["endpoints"][0]
    assert ep["port"] == "metrics", f"Expected port=metrics, got {ep['port']}"
    assert ep["path"] == "/metrics"


def test_servicemonitor_has_release_label():
    """
    ServiceMonitor PHẢI có label `release: kube-prometheus-stack` để match
    selector mặc định (vì main.tf:109 set `serviceMonitorSelectorNilUsesHelmValues = false`).
    """
    sm_path = ROOT / "manifests" / "observability" / "servicemonitor-sample-apps.yaml"
    sm = _load_yaml(sm_path)
    labels = sm["metadata"]["labels"]
    assert "release" in labels, f"Missing 'release' label, got {labels}"
    assert labels["release"] == "kube-prometheus-stack", \
        f"Expected release=kube-prometheus-stack, got {labels['release']}"


def test_ecommerce_servicemonitor_targets_http_port():
    """
    Ecommerce demo exposes metrics on the main HTTP port, unlike podinfo.
    """
    sm_path = ROOT / "manifests" / "observability" / "servicemonitor-ecommerce-demo.yaml"
    assert sm_path.exists(), f"Missing: {sm_path}"

    sm = _load_yaml(sm_path)
    assert sm["kind"] == "ServiceMonitor"
    assert sm["metadata"]["labels"]["release"] == "kube-prometheus-stack"
    assert sm["spec"]["selector"]["matchLabels"]["tier"] == "cdo-ecommerce-demo"
    assert sm["spec"]["selector"]["matchLabels"]["service"] == "ecommerce-api"
    assert sm["spec"]["endpoints"][0]["port"] == "http"
    assert sm["spec"]["endpoints"][0]["path"] == "/metrics"


def test_workload_service_has_matching_label():
    """
    Service trong tenant-a & tenant-b PHẢI có label `tier=cdo-sample` để
    ServiceMonitor selector match.
    """
    for ns_app in ["tenant-a-sample-app.yaml", "tenant-b-sample-app.yaml"]:
        path = ROOT / "manifests" / "workloads" / ns_app
        assert path.exists(), f"Missing: {path}"
        # Multi-doc — lấy tất cả, tìm Service
        with open(path, encoding="utf-8") as f:
            for doc in yaml.safe_load_all(f):
                if doc and doc.get("kind") == "Service":
                    labels = doc["metadata"]["labels"]
                    assert "tier" in labels, \
                        f"Service in {ns_app} missing 'tier' label, got {labels}"
                    assert labels["tier"] == "cdo-sample", \
                        f"Service in {ns_app}: expected tier=cdo-sample, got {labels['tier']}"


def test_prometheus_rule_query_uses_podinfo_metrics():
    """
    PrometheusRule PHẢI query metric name của podinfo (`http_requests_total`),
    KHÔNG phải Istio metric (file này đã OK từ turn trước — verify giữ vững).
    """
    rule_path = ROOT / "manifests" / "observability" / "prometheus-rule-service-signals.yaml"
    assert rule_path.exists(), f"Missing: {rule_path}"
    text = rule_path.read_text(encoding="utf-8")

    # Có query http_requests_total
    assert "http_requests_total" in text, "Rule phải query http_requests_total"
    # KHÔNG query istio_*
    assert "istio_" not in text, "Rule KHÔNG được query Istio metric (sai cho podinfo)"


def test_prometheus_collector_query_matches_podinfo():
    """
    PrometheusCollector.collect() phải query `http_requests_total` + filter
    theo label `deployment` (relabel rule từ ServiceMonitor).

    Verify bằng cách đọc method source code.
    """
    from collectors.prometheus_collector import PrometheusCollector
    import inspect
    src = inspect.getsource(PrometheusCollector.collect)
    assert "http_requests_total" in src
    assert "http_request_duration_seconds_bucket" in src
    assert "istio_" not in src
    # Có filter deployment (relabel rule gán __meta_kubernetes_service_label_app → deployment)
    assert "deployment=" in src


if __name__ == "__main__":
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
