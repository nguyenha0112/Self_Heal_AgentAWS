"""
PrometheusCollector — scrape 3 signal Service-level từ Prometheus / PromQL.

Signals:
  - service_error_rate       (A1) — % request 5xx hoặc non-zero gRPC
  - service_latency_p95      (A2) — p95 latency milliseconds
  - service_throughput_rps   (A3) — requests/second

Tích hợp:
  - HTTP GET `prometheus_api/v1/query` (Prometheus 2.x) hoặc
    `query?query=<promql>` trên Prometheus 1.x.
  - Auth: cluster internal (NetworkPolicy), không SigV4.
  - Endpoint env: `PROMETHEUS_URL` (mặc định `http://prometheus.monitoring:9090`).

Metric schema (sandbox dùng podinfo / stefanprodan/podinfo — service mesh optional):
  Podinfo expose Prometheus standard format (xem manifests/workloads/README.md):
    - http_requests_total{code, method, path}        (counter)
    - http_request_duration_seconds_bucket{le,...}   (histogram — seconds, KHÔNG phải ms)
    - label `code="500"` là 5xx, các giá trị < 500 là success.
  Khi tích hợp service mesh (sau khi rollout) thì đổi
  `http_*` → mesh_* + thêm label `destination_service_name`.

Bằng chứng pattern trong code:
  - `ai_client.py:_post()` đã có wrapper HTTP retry/backoff cho AI endpoint.
    PrometheusCollector dùng `requests.get()` trực tiếp + try/except (Prometheus
    là nguồn READ-ONLY, lỗi scrape → trả [] → caller tiếp tục với data khác).
  - Contract telemetry-contract §3 định value type:
      service_error_rate       → number 0.0-1.0
      service_latency_p95      → number (milliseconds)
      service_throughput_rps   → number
  - Đơn vị & range được ép trong `_to_value()` để đảm bảo AI Engine không bị 400.
    Lưu ý chuyển đổi đơn vị: histogram_seconds → latency_p95_milliseconds (×1000).
"""
from __future__ import annotations

import logging
from typing import Any

from config import CONFIG
from telemetry_contract import normalize_point

log = logging.getLogger(__name__)

try:
    import requests as _requests
    _HAS_HTTP = True
except ImportError:
    _HAS_HTTP = False


class PrometheusCollector:
    """
    Scrape 3 service-level signal qua PromQL.

    Mock mode (CDO_K8S_MOCK=true): không gọi Prometheus, trả mock value đúng
    schema để executor vẫn chạy hết loop ở chế độ offline.
    """

    name = "prometheus"
    supported_signals: tuple[str, ...] = (
        "service_error_rate",
        "service_latency_p95",
        "service_throughput_rps",
    )

    def __init__(self, base_url: str | None = None, cfg=CONFIG):
        self.base_url = base_url or getattr(cfg, "prometheus_url",
                                            "http://prometheus.monitoring:9090")
        self.cfg = cfg
        # Mock nếu k8s_mock=true HOẶC thiếu requests lib.
        self._mock = bool(getattr(cfg, "k8s_mock", False)) or not _HAS_HTTP

    def collect(self, *, tenant_id: str, namespace: str, deployment: str,
                tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Scrape 3 query song song (Prometheus instant query).

        PromQL theo podinfo (stefanprodan/podinfo) schema — đã verify trong
        sandbox khi apply ServiceMonitor `manifests/observability/servicemonitor-sample-apps.yaml`.
        Podinfo expose:
          - http_requests_total{code,method,path}               (counter)
          - http_request_duration_seconds_bucket{le,...}        (histogram)
        Khi tích hợp service mesh (production), đổi `http_*` → mesh metric
        + thêm label `destination_service_name`.

        Service identifier dùng label `deployment` (relabel rule trong ServiceMonitor
        đã gán từ `__meta_kubernetes_service_label_app` — xem manifest). Nếu
        label này thiếu (production chưa rollout ServiceMonitor) → PromQL trả
        [] → fallback mock.
        """
        if self._mock:
            return self._collect_mock(tenant_id, namespace, deployment)

        queries = {
            # 5xx / total — clamp [0.0, 1.0] trong _to_value()
            "service_error_rate":
                f'((sum(rate(http_requests_total{{deployment="{deployment}",'
                f'code=~"5.."}}[1m])) or vector(0)) + '
                f'(sum(rate(http_requests_total{{deployment="{deployment}",'
                f'status=~"5.."}}[1m])) or vector(0))) / '
                f'sum(rate(http_requests_total{{deployment="{deployment}"}}[1m]))',
            # p95 latency — query seconds, convert → milliseconds trong _to_value()
            "service_latency_p95":
                f'histogram_quantile(0.95, '
                f'sum(rate(http_request_duration_seconds_bucket{{'
                f'deployment="{deployment}"}}[1m])) by (le))',
            # RPS tổng (không phân biệt code)
            "service_throughput_rps":
                f'sum(rate(http_requests_total{{deployment="{deployment}"}}[1m]))',
        }
        out: list[dict[str, Any]] = []
        for signal_name, promql in queries.items():
            value = self._query(promql)
            if value is None:
                continue
            out.append(self._build_point(signal_name, value, tenant_id,
                                         namespace, deployment))
        return out

    # ---------- helpers ----------

    def _query(self, promql: str) -> float | None:
        """
        Gọi Prometheus instant query. Trả None nếu lỗi / không có data.
        """
        try:
            r = _requests.get(
                f"{self.base_url}/api/v1/query",
                params={"query": promql},
                timeout=self.cfg.ai_timeout_detect_s,
            )
            if r.status_code != 200:
                log.warning("prometheus query %s → %d", promql[:60], r.status_code)
                return None
            data = r.json().get("data", {}).get("result", [])
            if not data:
                return None
            return float(data[0]["value"][1])
        except Exception as e:
            log.warning("prometheus query failed: %s", e)
            return None

    def _build_point(self, signal_name: str, raw_value: float,
                     tenant_id: str, namespace: str, deployment: str) -> dict:
        """Build + normalize một telemetry point theo contract §3."""
        return normalize_point(
            {
                "ts": _now_iso(),
                "tenant_id": tenant_id,
                "service": deployment,
                "signal_name": signal_name,
                "value": self._to_value(signal_name, raw_value),
                "labels": {
                    "system": "K8S_NATIVE",
                    "namespace": namespace,
                    "deployment": deployment,
                    "source": "prometheus",
                },
            },
            tenant_id=tenant_id,
        )

    @staticmethod
    def _to_value(signal_name: str, raw: float) -> float:
        """
        Ép kiểu & range + đổi đơn vị cho đúng contract §3:
          - service_error_rate → clamp [0.0, 1.0]
          - service_latency_p95 → podinfo trả SECONDS → convert sang MILLISECONDS
                                   (×1000), sau đó round 1 chữ số thập phân
                                   cho AI dễ đọc.
          - service_throughput_rps → giữ nguyên, âm → 0
        """
        if signal_name == "service_error_rate":
            return max(0.0, min(1.0, raw))
        if signal_name == "service_latency_p95":
            # seconds → milliseconds
            return round(raw * 1000.0, 1)
        if signal_name == "service_throughput_rps":
            return max(0.0, raw)
        return raw

    def _collect_mock(self, tenant_id: str, namespace: str,
                      deployment: str) -> list[dict[str, Any]]:
        """
        Mock mode — sinh value giả lập nhưng ĐÚNG schema + range để executor
        vẫn pass validate & AI vẫn nhận được telemetry hợp lệ.

        GIÁ TRỊ INPUT ở đơn vị SOURCE (PromQL raw):
          - error_rate   = 0.08 (đã là tỷ lệ 0.0-1.0, không cần đổi)
          - latency_p95  = 0.85 SECONDS (podinfo histogram trả seconds)
                          → _to_value() sẽ convert sang 850.0 milliseconds
          - throughput   = 12.0 RPS (đã đúng đơn vị, chỉ clamp >= 0)
        """
        mock = {
            "service_error_rate": 0.08,
            "service_latency_p95": 0.85,        # seconds → _to_value() × 1000
            "service_throughput_rps": 12.0,
        }
        return [
            self._build_point(sig, val, tenant_id, namespace, deployment)
            for sig, val in mock.items()
        ]


def _now_iso() -> str:
    """RFC3339 UTC millisecond precision (contract §2.2 yêu cầu)."""
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + \
        f".{int((time.time() % 1) * 1000):03d}Z"
