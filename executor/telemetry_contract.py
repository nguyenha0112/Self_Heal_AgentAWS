"""
Telemetry contract helpers: normalize, validate, signal mapping, PII scrub.

Mục tiêu bám flow tài liệu:
raw telemetry -> adapter -> contract -> telemetry_window[] -> SQS -> forwarder -> /v1/detect
"""
from __future__ import annotations

import re
import time
from copy import deepcopy
from typing import Any

from errors import TelemetryContractError

ALLOWED_SIGNALS: frozenset[str] = frozenset({
    "service_error_rate",
    "service_latency_p95",
    "service_throughput_rps",
    "application_log_event",
    "distributed_trace_error_event",
    "container_resource_usage",
    "pod_oom_event",
    "container_restart_count",
    "service_unhealthy",
    "queue_backlog",
    "db_connection_pool_saturation",
    "secret_expiry_warning",
})

SIGNAL_ALIASES: dict[str, str] = {
    "error_rate": "service_error_rate",
    "latency_p95": "service_latency_p95",
    "throughput_rps": "service_throughput_rps",
    "log_event": "application_log_event",
    "trace_error_event": "distributed_trace_error_event",
    "memory_usage": "container_resource_usage",
    "oom_event": "pod_oom_event",
    "restart_count": "container_restart_count",
    "unhealthy": "service_unhealthy",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PASSWORD_RE = re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[^\s,;]+")
_TOKEN_RE = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._-]+|api[_-]?key\s*[:=]\s*[A-Za-z0-9._-]+)")
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d -]{8,}\d)\b")


def now_rfc3339() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def scrub_pii(value: Any) -> Any:
    if isinstance(value, str):
        value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
        value = _PASSWORD_RE.sub(r"\1=[REDACTED]", value)
        value = _TOKEN_RE.sub("[REDACTED_TOKEN]", value)
        value = _PHONE_RE.sub("[REDACTED_PHONE]", value)
        return value
    if isinstance(value, dict):
        return {str(k): scrub_pii(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_pii(v) for v in value]
    return value


def map_signal_name(raw_signal: str) -> str:
    signal = SIGNAL_ALIASES.get(raw_signal, raw_signal)
    if signal not in ALLOWED_SIGNALS:
        raise TelemetryContractError(f"unsupported_signal_name:{raw_signal}")
    return signal


def normalize_point(raw: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    point = deepcopy(raw)
    labels = point.get("labels") or {}
    signal_name = map_signal_name(str(point.get("signal_name", "")).strip())

    normalized = {
        "ts": point.get("ts") or now_rfc3339(),
        "tenant_id": point.get("tenant_id") or tenant_id,
        "service": point.get("service") or labels.get("deployment") or labels.get("service"),
        "signal_name": signal_name,
        "value": scrub_pii(point.get("value")),
        "labels": scrub_pii(labels),
    }
    validate_point(normalized, tenant_id=tenant_id)
    return normalized


def validate_point(point: dict[str, Any], *, tenant_id: str) -> None:
    required = ("ts", "tenant_id", "service", "signal_name", "value", "labels")
    for key in required:
        if key not in point or point[key] in (None, ""):
            raise TelemetryContractError(f"missing_field:{key}")
    if point["tenant_id"] != tenant_id:
        raise TelemetryContractError("tenant_id_mismatch")
    if point["signal_name"] not in ALLOWED_SIGNALS:
        raise TelemetryContractError(f"unsupported_signal_name:{point['signal_name']}")
    if not isinstance(point["labels"], dict):
        raise TelemetryContractError("labels_must_be_object")


def normalize_window(raw_points: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    if not raw_points:
        raise TelemetryContractError("empty_telemetry_window")
    return [normalize_point(point, tenant_id=tenant_id) for point in raw_points]
