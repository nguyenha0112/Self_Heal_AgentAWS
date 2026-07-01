"""
LogCollector — scrape application log event + distributed trace span error.

Signals:
  - application_log_event         (A4) — log ERROR level + stack trace
  - distributed_trace_error_event (A5) — trace span có error status

Tích hợp:
  - AWS CloudWatch Logs Insights (Pull API) — query gần nhất `n` phút
  - Hoặc OpenTelemetry Collector endpoint `/v1/logs` (Push)
  - Env: `LOG_SOURCE=cloudwatch|otel` (default `cloudwatch`)
        `CW_LOG_GROUP=/aws/eks/...` (khi source=cloudwatch)
        `OTEL_LOGS_ENDPOINT=http://otel-collector.monitoring:4318`

Bằng chứng pattern trong code:
  - `k8s_client.py:164-185` đã có `get_recent_pod_logs()` — đây là
    fallback local (pods/log subresource). LogCollector dùng cluster-wide
    log API để scrape nhanh hơn & không phụ thuộc RBAC `pods/log`.
  - Contract §3 quy định value:
      application_log_event         → string (có thể chứa stack trace)
      distributed_trace_error_event → number (HTTP status / gRPC code)
  - `telemetry_contract.py:scrub_pii()` đã có sẵn 4 pattern PII — được áp
    dụng qua `normalize_point()`.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from config import CONFIG
from telemetry_contract import normalize_point, scrub_pii

log = logging.getLogger(__name__)

try:
    import boto3 as _boto3
    _HAS_BOTO = True
except ImportError:
    _HAS_BOTO = False

try:
    import requests as _requests
    _HAS_HTTP = True
except ImportError:
    _HAS_HTTP = False


class LogCollector:
    """
    Scrape 2 signal log/trace từ CloudWatch Logs Insights hoặc OTel.

    Mode chọn bằng env `LOG_SOURCE`:
      - `cloudwatch`: dùng boto3 (cần IRSA đã có sẵn cho executor pod)
      - `otel`: dùng HTTP POST sang OTel collector
      - `mock`: trả mock data (dev/offline)
    """

    name = "logs"
    supported_signals: tuple[str, ...] = (
        "application_log_event",
        "distributed_trace_error_event",
    )

    def __init__(self, cfg=CONFIG):
        self.cfg = cfg
        self.source = getattr(cfg, "log_source", "mock")

    def collect(self, *, tenant_id: str, namespace: str, deployment: str,
                tenant_namespace: str) -> list[dict[str, Any]]:
        if self.source == "cloudwatch":
            return self._collect_cloudwatch(tenant_id, namespace, deployment)
        if self.source == "otel":
            return self._collect_otel(tenant_id, namespace, deployment)
        return self._collect_mock(tenant_id, namespace, deployment)

    # ---------- CloudWatch Logs Insights ----------

    def _collect_cloudwatch(self, tenant_id: str, namespace: str,
                            deployment: str) -> list[dict[str, Any]]:
        """
        Query CloudWatch Logs Insights:
          - application_log_event: filter `level=ERROR AND @logStream like /<deployment>/`
          - distributed_trace_error_event: filter `httpStatus >= 500`
        """
        if not _HAS_BOTO:
            log.warning("boto3 chưa cài — fallback mock")
            return self._collect_mock(tenant_id, namespace, deployment)

        log_group = getattr(self.cfg, "cw_log_group",
                            f"/aws/eks/{self.cfg.cluster_name}/application")
        try:
            cw = _boto3.client("logs", region_name=self.cfg.aws_region)
            # 1. application log event
            log_query = (
                f'fields @timestamp, @message, @logStream '
                f'| filter kubernetes.namespace_name = "{namespace}" '
                f'and kubernetes.labels.app = "{deployment}" '
                f'and level = "ERROR" '
                f'| sort @timestamp desc | limit 5'
            )
            log_resp = cw.start_query(
                logGroupName=log_group,
                startTime=int(time.time()) - 300,
                endTime=int(time.time()),
                queryString=log_query,
            )
            log_results = self._wait_query(cw, log_resp["queryId"])
            out = [self._build_log_point(m, tenant_id, namespace, deployment)
                   for m in log_results]

            # 2. trace error event
            trace_query = (
                f'fields @timestamp, http.status_code, traceId, spanId, http.url '
                f'| filter kubernetes.namespace_name = "{namespace}" '
                f'and kubernetes.labels.app = "{deployment}" '
                f'and http.status_code >= 500 '
                f'| sort @timestamp desc | limit 5'
            )
            trace_resp = cw.start_query(
                logGroupName=log_group,
                startTime=int(time.time()) - 300,
                endTime=int(time.time()),
                queryString=trace_query,
            )
            trace_results = self._wait_query(cw, trace_resp["queryId"])
            out.extend(self._build_trace_points(
                trace_results, tenant_id, namespace, deployment))
            return out
        except Exception as e:
            log.warning("cloudwatch logs query failed: %s", e)
            return []

    @staticmethod
    def _wait_query(client, query_id: str, max_wait_s: int = 5) -> list[dict]:
        """Poll Logs Insights query đến khi xong hoặc timeout."""
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            r = client.get_query_results(queryId=query_id)
            if r["status"] in ("Complete", "Failed", "Cancelled"):
                return r.get("results", [])
            time.sleep(0.5)
        return []

    # ---------- OTel HTTP ----------

    def _collect_otel(self, tenant_id: str, namespace: str,
                      deployment: str) -> list[dict[str, Any]]:
        """
        Query OTel collector — collector expose `/v1/logs` (push) hoặc scrape
        endpoint tuỳ implementation. Ở đây dùng Logs API Export.
        """
        if not _HAS_HTTP:
            return self._collect_mock(tenant_id, namespace, deployment)

        endpoint = getattr(self.cfg, "otel_logs_endpoint",
                           "http://otel-collector.monitoring:4318/v1/logs")
        try:
            r = _requests.get(
                endpoint,
                params={
                    "namespace": namespace,
                    "deployment": deployment,
                    "level": "ERROR",
                    "window_s": "300",
                },
                timeout=self.cfg.ai_timeout_detect_s,
            )
            if r.status_code != 200:
                return []
            data = r.json()
            return [self._build_log_point(m, tenant_id, namespace, deployment)
                    for m in data.get("logs", [])]
        except Exception as e:
            log.warning("otel log query failed: %s", e)
            return []

    # ---------- helpers ----------

    def _build_log_point(self, msg: dict, tenant_id: str,
                         namespace: str, deployment: str) -> dict:
        """Build application_log_event point."""
        text = msg.get("@message") or msg.get("message") or str(msg)
        return normalize_point(
            {
                "ts": _now_iso(),
                "tenant_id": tenant_id,
                "service": deployment,
                "signal_name": "application_log_event",
                "value": scrub_pii(text),
                "labels": {
                    "system": "K8S_NATIVE",
                    "namespace": namespace,
                    "deployment": deployment,
                    "level": "ERROR",
                    "source": "logs",
                },
            },
            tenant_id=tenant_id,
        )

    def _build_trace_points(self, results: list[dict], tenant_id: str,
                             namespace: str, deployment: str) -> list[dict]:
        """Build distributed_trace_error_event point(s)."""
        out: list[dict[str, Any]] = []
        for row in results:
            field_map = {f["field"]: f["value"] for f in row}
            status = int(field_map.get("http.status_code", 500))
            out.append(normalize_point(
                {
                    "ts": _now_iso(),
                    "tenant_id": tenant_id,
                    "service": deployment,
                    "signal_name": "distributed_trace_error_event",
                    "value": status,
                    "labels": {
                        "system": "K8S_NATIVE",
                        "namespace": namespace,
                        "deployment": deployment,
                        "trace_id": field_map.get("traceId", ""),
                        "span_id": field_map.get("spanId", ""),
                        "operation": field_map.get("http.url", ""),
                        "source": "logs",
                    },
                },
                tenant_id=tenant_id,
            ))
        return out

    def _collect_mock(self, tenant_id: str, namespace: str,
                      deployment: str) -> list[dict[str, Any]]:
        """Mock: 1 log error + 1 trace error."""
        return [
            normalize_point(
                {
                    "ts": _now_iso(),
                    "tenant_id": tenant_id,
                    "service": deployment,
                    "signal_name": "application_log_event",
                    "value": ("NullPointerException: Cannot invoke "
                              f"'Database.connect()' at {deployment}.java:102"),
                    "labels": {
                        "system": "K8S_NATIVE",
                        "namespace": namespace,
                        "deployment": deployment,
                        "level": "ERROR",
                        "source": "logs_mock",
                    },
                },
                tenant_id=tenant_id,
            ),
            normalize_point(
                {
                    "ts": _now_iso(),
                    "tenant_id": tenant_id,
                    "service": deployment,
                    "signal_name": "distributed_trace_error_event",
                    "value": 503,
                    "labels": {
                        "system": "K8S_NATIVE",
                        "namespace": namespace,
                        "deployment": deployment,
                        "operation": f"POST /{deployment}/checkout",
                        "source": "logs_mock",
                    },
                },
                tenant_id=tenant_id,
            ),
        ]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + \
        f".{int((time.time() % 1) * 1000):03d}Z"