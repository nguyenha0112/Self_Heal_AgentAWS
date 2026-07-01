"""
K8sMetricsCollector — scrape metrics từ Kubernetes Metrics Server / cAdvisor.

Signals:
  - container_resource_usage  (B1) — memory working_set bytes
  - service_unhealthy          (B4) — extend watcher với probe failure (Phase 2)

Tích hợp:
  - `metrics.k8s.io/v1beta1` PodMetrics (Metrics Server đã có sẵn trong EKS).
  - Endpoint: K8sClient.get_pod_metrics(namespace, deployment).

Bằng chứng pattern trong code:
  - `k8s_client.py:155-185` đã có `list_pods_raw()` & `get_recent_pod_logs()`
    dùng `kubernetes` client. K8sMetricsCollector mở rộng K8sClient thêm
    method `get_pod_metrics()`.
  - Contract §3 quy định value `container_resource_usage` là INTEGER bytes
    (không phải string như OOM event).
  - Failure mode: nếu Metrics Server chưa deploy (dev mode) → trả [].
    telemetry-contract §2.5 yêu cầu graceful degradation khi source missing.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from config import CONFIG
from k8s_client import K8sClient
from telemetry_contract import normalize_point

log = logging.getLogger(__name__)


class K8sMetricsCollector:
    """
    Scrape container resource metrics từ K8s Metrics Server.

    Mock mode: trả mock value (1GB working_set) để executor chạy hết loop.
    """

    name = "k8s_metrics"
    supported_signals: tuple[str, ...] = (
        "container_resource_usage",
    )

    def __init__(self, k8s: K8sClient | None = None, cfg=CONFIG):
        self.k8s = k8s or K8sClient(in_cluster=True)
        self.cfg = cfg

    def collect(self, *, tenant_id: str, namespace: str, deployment: str,
                tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Trả về 0 hoặc nhiều point `container_resource_usage` (1 point per pod
        thuộc deployment).

        Mỗi point có value là INTEGER bytes (contract §3 yêu cầu number,
        watcher.py:53 dùng string cho OOM event — khác signal).
        """
        if not getattr(self.k8s, "enabled", False):
            return self._mock_points(tenant_id, namespace, deployment)

        try:
            metrics = self.k8s.get_pod_metrics(namespace, deployment)
        except Exception as e:
            log.warning("metrics scrape failed for %s/%s: %s",
                        namespace, deployment, e)
            return []

        out: list[dict[str, Any]] = []
        for pod_name, container_name, mem_bytes in metrics:
            out.append(self._build_point(
                signal_name="container_resource_usage",
                value=int(mem_bytes),
                tenant_id=tenant_id,
                namespace=namespace,
                deployment=deployment,
                pod_name=pod_name,
                container_name=container_name,
            ))
        return out

    # ---------- helpers ----------

    def _build_point(self, *, signal_name: str, value: int,
                     tenant_id: str, namespace: str, deployment: str,
                     pod_name: str, container_name: str) -> dict:
        """Build + normalize một point `container_resource_usage`."""
        return normalize_point(
            {
                "ts": _now_iso(),
                "tenant_id": tenant_id,
                "service": deployment,
                "signal_name": signal_name,
                "value": value,
                "labels": {
                    "system": "K8S_NATIVE",
                    "namespace": namespace,
                    "deployment": deployment,
                    "pod_name": pod_name,
                    "container": container_name,
                    "source": "metrics_server",
                },
            },
            tenant_id=tenant_id,
        )

    def _mock_points(self, tenant_id: str, namespace: str,
                     deployment: str) -> list[dict[str, Any]]:
        """
        Mock 2 pods × ~1GB working_set — đủ để AI phân tích memory pressure.
        """
        return [
            self._build_point(
                signal_name="container_resource_usage",
                value=1073741824,
                tenant_id=tenant_id, namespace=namespace,
                deployment=deployment,
                pod_name=f"{deployment}-5f8d9b7c-xyz12",
                container_name="main",
            ),
            self._build_point(
                signal_name="container_resource_usage",
                value=858993459,
                tenant_id=tenant_id, namespace=namespace,
                deployment=deployment,
                pod_name=f"{deployment}-5f8d9b7c-abc34",
                container_name="main",
            ),
        ]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + \
        f".{int((time.time() % 1) * 1000):03d}Z"