"""
Signal Collector interface — Strategy pattern cho 4 nguồn telemetry khác nhau.

Bối cảnh:
  Contract telemetry-contract §3 quy định 12 `signal_name` thuộc 4 lớp:
    A. Application & Service      (5 signal)
    B. Infrastructure & Container (4 signal)
    C. Middleware & Dependencies  (2 signal)
    D. Security & Compliance      (1 signal)

  Mỗi signal có một nguồn dữ liệu tự nhiên. Watcher hiện tại (watcher.py)
  chỉ scrape K8s pod status → cover được 4/12 signal (OOM, crash, restart,
  unhealthy từ ImagePull). Để cover đủ 12, executor cần hỏi thêm các nguồn:

    +-----------------------+--------------------------+--------------------------+
    | Signal                | Source tự nhiên          | Collector                |
    +-----------------------+--------------------------+--------------------------+
    | service_error_rate    | Prometheus query         | PrometheusCollector      |
    | service_latency_p95   | Prometheus histogram     | PrometheusCollector      |
    | service_throughput_rps| Prometheus counter       | PrometheusCollector      |
    | application_log_event | Fluentd / OTel log pipe  | LogCollector             |
    | distributed_trace_... | OTel trace pipeline      | LogCollector             |
    | container_resource_.. | Metrics Server / cAdvisor| K8sMetricsCollector      |
    | pod_oom_event         | K8s pod status           | (watcher.py đã có)       |
    | container_restart_..  | K8s pod status           | (watcher.py đã có)       |
    | service_unhealthy     | K8s pod status + probe   | (watcher.py + mở rộng)   |
    | queue_backlog         | SQS / RabbitMQ API       | ExternalCollector        |
    | db_connection_pool_.. | DB exporter              | ExternalCollector        |
    | secret_expiry_warning | Secrets Manager event    | ExternalCollector        |
    +-----------------------+--------------------------+--------------------------+

SignalCollector là abstract base: mỗi concrete collector có method `collect()`
trả về list các telemetry point đúng schema contract §3.

Bằng chứng tích hợp trong code:
  - `watcher.py:67-83` đã có pattern poll loop cho K8s pod status — đây là
    concrete collector đầu tiên nhưng chưa được gom vào interface chung.
  - `main.py:50-66` `handle_incident()` nhận `telemetry_window` đã build sẵn,
    KHÔNG phân biệt signal nào đến từ nguồn nào — đây là lý do cần SignalCollector
    để tổng quát hoá việc "thu thập khi cần" trước khi gọi AI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SignalCollector(ABC):
    """
    Base class cho mọi collector.

    Mỗi collector biết:
      - `name`: tên định danh (dùng trong log + audit)
      - `supported_signals`: tuple các signal_name (theo enum contract §3) mà
        collector này CÓ THỂ sinh ra — không phải luôn sinh ra, mà là "nếu có
        data thì tôi map sang signal này".
      - `collect(...)`: method thực thi scrape, trả list các point theo schema
        telemetry-contract §3 (đã validate, đã PII-scrub).
    """

    name: str = "abstract"
    supported_signals: tuple[str, ...] = ()

    @abstractmethod
    def collect(self, *, tenant_id: str, namespace: str, deployment: str,
                tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Scrape telemetry từ nguồn của collector, trả list các point đúng schema.

        Trả [] nếu không có data (KHÔNG raise) — caller sẽ merge các collector
        để build `telemetry_window` hoàn chỉnh trước khi gọi /v1/detect.

        Contract cho từng point: telemetry_contract.py:normalize_point() — đã
        có sẵn, collector CHỈ CẦN gọi `normalize_point()` để đảm bảo đúng schema.
        """

    def _signal_in_scope(self, signal_name: str) -> bool:
        """Helper: signal có thuộc phạm vi collector này không."""
        return signal_name in self.supported_signals


class CollectorRegistry:
    """
    Gom các collector và dispatch `collect()` theo `signal_name`.

    Khi AI detect một fault type (e.g. `database_connection_failure`), executor
    cần quyết định scrape signal nào. `CollectorRegistry` cung cấp:

      - `collect_for_signal(signal_name, ...)`: gọi collector sở hữu signal đó
      - `collect_all(...)`: gọi TẤT CẢ collector (dùng khi AI cần full context)
      - `supported_signals`: set tất cả signal mà registry biết scrape được

    Bằng chứng cần thiết trong code:
      - watcher.py hiện chỉ map 4 waiting_reason → signal. Để AI yêu cầu signal
        cụ thể (vd `queue_backlog` khi nghi ngờ worker chậm), executor phải
        biết collector nào scrape được signal đó. Registry là câu trả lời.
    """

    def __init__(self, collectors: list[SignalCollector] | None = None):
        self._by_signal: dict[str, SignalCollector] = {}
        self._all: list[SignalCollector] = []
        for c in (collectors or []):
            self.register(c)

    def register(self, collector: SignalCollector) -> None:
        self._all.append(collector)
        for sig in collector.supported_signals:
            # Nếu đã có collector cho signal này → giữ collector đầu tiên
            # (ưu tiên collector đăng ký trước).
            self._by_signal.setdefault(sig, collector)

    @property
    def supported_signals(self) -> set[str]:
        return set(self._by_signal.keys())

    def collect_for_signal(self, signal_name: str, *,
                            tenant_id: str, namespace: str, deployment: str,
                            tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Scrape đúng collector sở hữu `signal_name`.

        Trả [] nếu signal không có collector (fallback: caller nên log warning
        và KHÔNG gọi AI với signal không scrape được — tránh gửi data rỗng).
        """
        collector = self._by_signal.get(signal_name)
        if collector is None:
            return []
        return collector.collect(
            tenant_id=tenant_id,
            namespace=namespace,
            deployment=deployment,
            tenant_namespace=tenant_namespace,
        )

    def collect_all(self, *, tenant_id: str, namespace: str, deployment: str,
                    tenant_namespace: str) -> list[dict[str, Any]]:
        """
        Scrape TẤT CẢ collector đang đăng ký. Trả list các point đã gộp.

        Dùng khi:
          - Watcher phát hiện fault mà không rõ root cause (cần full context)
          - AI yêu cầu `telemetry_window` đa chiều để chẩn đoán
        """
        out: list[dict[str, Any]] = []
        for c in self._all:
            try:
                out.extend(c.collect(
                    tenant_id=tenant_id,
                    namespace=namespace,
                    deployment=deployment,
                    tenant_namespace=tenant_namespace,
                ))
            except Exception:
                # Một collector lỗi KHÔNG được chặn các collector khác —
                # telemetry-contract §2.5.B yêu cầu graceful degradation.
                continue
        return out