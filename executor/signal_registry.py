"""
SignalRegistry — ánh xạ "lỗi gì → scrape signal nào".

Bối cảnh:
  Telemetry contract định 12 signal, mỗi fault có 1-3 signal LIÊN QUAN nhất.
  Khi CDO detect được 1 incident (từ K8s watcher / Alertmanager webhook /
  manual injection), executor cần quyết định:

    1. Fault type là gì?
    2. Signal nào cần scrape để AI có đủ context chẩn đoán?
    3. Collector nào sở hữu signal đó?

  File này đóng vai trò "translation table" — KHÔNG scrape, KHÔNG gọi AI,
  CHỈ quyết định collector nào sẽ được gọi khi có fault X.

Bằng chứng pattern trong code:
  - `watcher.py:29-35` `_WAITING_REASON_MAP` đã có K8s waiting_reason →
    signal_name mapping. Đây là 1 sub-case của SignalRegistry (phần K8s
    pod status). File này MỞ RỘNG pattern này ra toàn bộ 12 signal.
  - `pre_decide_gate.py` quyết định "có proceed không", SignalRegistry quyết
    định "scrape gì trước khi proceed".
  - `main.py:64` `normalized_window = self.adapter.build_window(telemetry_window)`
    hiện nhận window ĐÃ build sẵn từ watcher. Mở rộng: cho phép build window
    BẰNG registry khi fault type chưa rõ → registry.collect_all() rồi merge.

Cách dùng:
  >>> registry = default_registry(collectors=[K8sWatcherAsCollector(), ...])
  >>> # Cách 1: theo fault type (preferred — collector đã biết root cause)
  >>> window = registry.collect_for_fault("OOM_KILL", tenant_id=..., namespace=...)
  >>> # Cách 2: theo signal name (caller biết signal nào cần)
  >>> window = registry.collect_for_signal("service_error_rate", ...)
  >>> # Cách 3: scrape hết (fallback khi không biết fault)
  >>> window = registry.collect_all(...)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from collectors import CollectorRegistry, SignalCollector

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Fault type → signals mapping
# ---------------------------------------------------------------------
#
# Mỗi fault ánh xạ tới danh sách signal LIÊN QUAN NHẤT để AI có context.
# Thứ tự trong list = thứ tự ưu tiên (signal đầu tiên quan trọng nhất).
#
# `fault_type` ở đây là domain-level fault (string) — có thể đến từ:
#   - K8s pod waiting_reason (xem watcher.py _WAITING_REASON_MAP)
#   - Alertmanager alert label (vd `alertname=KubePodOOMKilled`)
#   - Manual injector (vd scenarios/tc01_service_stuck.json)
#
# Mapping table được suy ra từ runbook phổ biến:
#   OOM_KILL          → memory issue  → PATCH_MEMORY_LIMIT
#   CRASH_LOOP        → restart issue → ROLLOUT_UNDO hoặc restart
#   LATENCY_SPIKE     → perf issue    → SCALE_REPLICAS hoặc restart
#   ERROR_RATE_HIGH   → 5xx issue     → restart / rollback
#   BAD_DEPLOY        → bad config    → ROLLOUT_UNDO
#   QUEUE_BACKLOG     → worker chậm   → SCALE_REPLICAS
#   DB_POOL_SATURATION→ connection    → restart / pool config
#   CERT_EXPIRY       → security      → ROTATE_SECRET
#   MEMORY_PRESSURE   → memory        → PATCH_MEMORY_LIMIT
#   SERVICE_STUCK     → unknown       → scrape full context
#
FAULT_TO_SIGNALS: dict[str, list[str]] = {
    # ---- Infrastructure & Container ----
    "OOM_KILL": [
        "pod_oom_event",
        "container_resource_usage",       # xác nhận memory hiện tại
        "container_restart_count",        # đếm số lần restart gần đây
    ],
    "CRASH_LOOP": [
        "container_restart_count",
        "application_log_event",          # stack trace root cause
        "service_unhealthy",              # probe failure
    ],
    "BAD_DEPLOY": [
        "service_unhealthy",              # probe fail do image pull
        "container_restart_count",
        "application_log_event",
    ],
    "MEMORY_PRESSURE": [
        "container_resource_usage",
        "service_latency_p95",            # memory pressure → GC → latency tăng
        "pod_oom_event",                  # nguy cơ OOM
    ],
    # ---- Application & Service ----
    "ERROR_RATE_HIGH": [
        "service_error_rate",
        "application_log_event",          # exception messages
        "distributed_trace_error_event",  # 5xx trace
    ],
    "LATENCY_SPIKE": [
        "service_latency_p95",
        "service_throughput_rps",         # xem tải hiện tại
        "container_resource_usage",       # GC liên quan memory
    ],
    "SERVICE_STUCK": [
        "service_latency_p95",
        "service_error_rate",
        "service_unhealthy",
        "application_log_event",
    ],
    # ---- Middleware & Dependencies ----
    "QUEUE_BACKLOG": [
        "queue_backlog",
        "service_throughput_rps",        # xem consumption rate
        "container_resource_usage",       # worker có OOM không
    ],
    "DB_POOL_SATURATION": [
        "db_connection_pool_saturation",
        "service_latency_p95",            # pool đầy → query chậm
        "service_error_rate",             # pool đầy → 5xx timeout
    ],
    # ---- Security & Compliance ----
    "CERT_EXPIRY": [
        "secret_expiry_warning",
        "service_unhealthy",              # cert hết hạn → TLS fail
    ],
    # ---- Catch-all (khi không biết fault) ----
    "UNKNOWN": [
        # Scrape tất cả các signal có sẵn — đắt nhưng safe.
        # Registry.collect_all() sẽ tự loop qua tất cả collector.
    ],
}


# CDO internal fault types -> AI Engine platform-profile fault types.
CDO_TO_AI_FAULT_TYPE: dict[str, str] = {
    "OOM_KILL": "mem",
    "MEMORY_PRESSURE": "mem",
    "CRASH_LOOP": "mem",
    "BAD_DEPLOY": "cpu",
    "ERROR_RATE_HIGH": "loss",
    "LATENCY_SPIKE": "delay",
    "SERVICE_STUCK": "delay",
    "QUEUE_BACKLOG": "delay",
    "DB_POOL_SATURATION": "socket",
    "CERT_EXPIRY": "cpu",
    "UNKNOWN": "f1",
}


def to_ai_fault_type(fault_type: str | None) -> str | None:
    if fault_type is None:
        return None
    return CDO_TO_AI_FAULT_TYPE.get(fault_type, fault_type)


# ---------------------------------------------------------------------
# K8s waiting_reason → fault_type (mở rộng của watcher.py)
# ---------------------------------------------------------------------
# watcher.py đã có `_WAITING_REASON_MAP` riêng. Đây là canonical mapping
# (khớp 1-1) để các phần khác của code tham chiếu.
K8S_WAITING_TO_FAULT: dict[str, str] = {
    "OOMKilled": "OOM_KILL",
    "CrashLoopBackOff": "CRASH_LOOP",
    "Error": "CRASH_LOOP",
    "ImagePullBackOff": "BAD_DEPLOY",
    "ErrImagePull": "BAD_DEPLOY",
    "CreateContainerConfigError": "BAD_DEPLOY",
}


@dataclass
class SignalRequest:
    """
    Kết quả của registry.resolve() — cho caller biết cần scrape gì.

    Ví dụ:
        req = registry.resolve("OOM_KILL", tenant_id=..., namespace=..., ...)
        # req.fault_type = "OOM_KILL"
        # req.signals = ["pod_oom_event", "container_resource_usage", ...]
        # req.collect = ["k8s_metrics"]  # các collector sẽ được gọi
    """
    fault_type: str
    signals: list[str]
    collector_names: list[str] = field(default_factory=list)


class SignalRegistry:
    """
    Bộ não quyết định "khi có fault X → scrape signal Y từ collector Z".

    Tách khỏi CollectorRegistry:
      - CollectorRegistry: "collector nào scrape được signal nào"
      - SignalRegistry (đây): "fault nào cần signal nào" + dispatch

    Hai registry compose với nhau: SignalRegistry.resolve() trả danh sách
    signal → caller dùng CollectorRegistry.collect_for_signal() để scrape.
    """

    def __init__(self, fault_table: dict[str, list[str]] | None = None,
                 k8s_table: dict[str, str] | None = None,
                 collector_registry: CollectorRegistry | None = None):
        self._fault_table = fault_table or FAULT_TO_SIGNALS
        self._k8s_table = k8s_table or K8S_WAITING_TO_FAULT
        self._collectors = collector_registry or CollectorRegistry()

    # ----- injection -----

    def set_collector_registry(self, registry: CollectorRegistry) -> None:
        """Inject CollectorRegistry sau khi khởi tạo."""
        self._collectors = registry

    # ----- resolution -----

    def resolve(self, fault_type: str) -> SignalRequest:
        """
        Trả SignalRequest cho fault_type — gồm signals + collector names.

        Không scrape, chỉ tính toán. Caller dùng `collectors.collect_for_signal()`
        để lấy data.
        """
        signals = self._fault_table.get(fault_type, self._fault_table["UNKNOWN"])
        collector_names: list[str] = []
        for sig in signals:
            c = self._collectors._by_signal.get(sig)  # type: ignore[attr-defined]
            if c and c.name not in collector_names:
                collector_names.append(c.name)
        return SignalRequest(
            fault_type=fault_type,
            signals=signals,
            collector_names=collector_names,
        )

    def resolve_from_k8s_reason(self, waiting_reason: str) -> SignalRequest:
        """Convenience: K8s waiting_reason → fault_type → SignalRequest."""
        fault = self._k8s_table.get(waiting_reason, "UNKNOWN")
        return self.resolve(fault)

    # ----- collection -----

    def collect_for_fault(self, fault_type: str, *,
                           tenant_id: str, namespace: str, deployment: str,
                           tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Một call duy nhất: resolve fault → scrape signals → trả telemetry window.

        Dùng trong `main.handle_incident()` thay vì gọi từng collector thủ công.
        """
        req = self.resolve(fault_type)
        out: list[dict[str, Any]] = []
        for sig in req.signals:
            out.extend(self._collectors.collect_for_signal(
                signal_name=sig,
                tenant_id=tenant_id,
                namespace=namespace,
                deployment=deployment,
                tenant_namespace=tenant_namespace,
            ))
        return out

    def collect_for_signal(self, signal_name: str, *,
                            tenant_id: str, namespace: str, deployment: str,
                            tenant_namespace: str) -> list[dict[str, Any]]:
        """Shortcut: scrape đúng 1 signal."""
        return self._collectors.collect_for_signal(
            signal_name=signal_name,
            tenant_id=tenant_id,
            namespace=namespace,
            deployment=deployment,
            tenant_namespace=tenant_namespace,
        )

    def collect_all(self, *, tenant_id: str, namespace: str,
                     deployment: str, tenant_namespace: str) -> list[dict[str, Any]]:
        """Fallback khi không biết fault — scrape hết collector đã đăng ký."""
        return self._collectors.collect_all(
            tenant_id=tenant_id,
            namespace=namespace,
            deployment=deployment,
            tenant_namespace=tenant_namespace,
        )


# ---------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------

def default_registry(k8s_client=None, cfg=None) -> SignalRegistry:
    """
    Tạo SignalRegistry mặc định với 4 concrete collector đã có.

    Các collector được đăng ký theo thứ tự:
      1. K8sMetricsCollector  (container_resource_usage)
      2. PrometheusCollector  (3 service signal)
      3. LogCollector         (log + trace)
      4. ExternalCollector    (queue + db + secret)

    K8sWatcher (pod status — OOM/crash/restart/unhealthy) đã được gom vào
    `watcher.py` — KHÔNG đăng ký ở đây vì caller (main.py) đã poll watcher
    riêng trước khi gọi registry.

    Bằng chứng: main.py:248-258 đã có watch_loop() gọi watcher.poll → fault
    events → handle_incident(). Registry dùng trong handle_incident() để
    scrape thêm signal ngoài watcher.
    """
    from collectors.k8s_metrics_collector import K8sMetricsCollector
    from collectors.prometheus_collector import PrometheusCollector
    from collectors.log_collector import LogCollector
    from collectors.external_collector import ExternalCollector

    cr = CollectorRegistry([
        K8sMetricsCollector(k8s=k8s_client, cfg=cfg) if cfg else K8sMetricsCollector(k8s=k8s_client),
        PrometheusCollector(cfg=cfg) if cfg else PrometheusCollector(),
        LogCollector(cfg=cfg) if cfg else LogCollector(),
        ExternalCollector(cfg=cfg) if cfg else ExternalCollector(),
    ])
    return SignalRegistry(collector_registry=cr)
