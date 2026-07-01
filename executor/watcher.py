"""
Kubernetes pod-status watcher.

Polls pods in tenant namespaces and emits telemetry points that match the AI
Engine TelemetryPoint schema. Event-like Kubernetes signals are encoded as
numeric flags/counts, with pod/container details stored in labels.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config import CONFIG


_WAITING_REASON_MAP: dict[str, tuple[str, str]] = {
    "OOMKilled": ("pod_oom_event", "OOM_KILL"),
    "CrashLoopBackOff": ("container_restart_count", "CRASH_LOOP"),
    "Error": ("container_restart_count", "CRASH_LOOP"),
    "ImagePullBackOff": ("service_unhealthy", "BAD_DEPLOY"),
    "ErrImagePull": ("service_unhealthy", "BAD_DEPLOY"),
}
_OOM_EXIT_CODE = 137


def _now_rfc3339_ms() -> str:
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + \
        f".{int((now % 1) * 1000):03d}Z"


def _waiting_signal(reason: str, pod_name: str, container: str,
                    restart_count: int) -> tuple[str, Any, dict[str, Any]]:
    signal_name, _ = _WAITING_REASON_MAP.get(reason, ("service_unhealthy", "UNKNOWN"))
    detail = {
        "pod_name": pod_name,
        "container": container,
        "k8s_reason": reason,
    }
    if signal_name == "container_restart_count":
        return signal_name, restart_count, detail
    if signal_name == "pod_oom_event":
        detail["exit_code"] = _OOM_EXIT_CODE
        return signal_name, 1.0, detail
    return "service_unhealthy", 1.0, detail


@dataclass
class FaultEvent:
    namespace: str
    service: str
    deployment: str
    suspected_fault_type: str
    telemetry_window: list[dict] = field(default_factory=list)


def collect_fault_events(k8s, namespaces: tuple[str, ...], cfg=CONFIG) -> list[FaultEvent]:
    events: list[FaultEvent] = []
    for ns in namespaces:
        pod_list = k8s.list_pods_raw(ns)
        if pod_list is None:
            continue
        for pod in pod_list.items:
            if not pod.status or not pod.status.container_statuses:
                continue
            ev = _inspect_pod(pod, ns, cfg)
            if ev is not None:
                events.append(ev)
    return events


def _inspect_pod(pod, namespace: str, cfg) -> FaultEvent | None:
    deployment = _infer_deployment(pod)
    labels = pod.metadata.labels or {}
    service = labels.get("app", deployment)
    pod_name = pod.metadata.name
    signals: list[dict] = []
    fault_type: str | None = None

    for cs in pod.status.container_statuses:
        rc = cs.restart_count or 0
        if cs.state and cs.state.waiting:
            reason = cs.state.waiting.reason or ""
            mapped = _WAITING_REASON_MAP.get(reason)
            if mapped:
                fault_type = fault_type or mapped[1]
                signal_name, value, detail = _waiting_signal(reason, pod_name, cs.name, rc)
                signals.append(_signal(
                    service, namespace, deployment, signal_name, value, cfg,
                    pod_name=pod_name, container=cs.name, extra_labels=detail,
                ))

        if cs.last_state and cs.last_state.terminated:
            if cs.last_state.terminated.exit_code == _OOM_EXIT_CODE:
                fault_type = fault_type or "OOM_KILL"
                signals.append(_signal(
                    service, namespace, deployment, "pod_oom_event", 1.0, cfg,
                    pod_name=pod_name,
                    container=cs.name,
                    extra_labels={
                        "k8s_reason": "OOMKilled",
                        "exit_code": _OOM_EXIT_CODE,
                    },
                ))

        if rc > cfg.restart_count_threshold:
            fault_type = fault_type or "CRASH_LOOP"
            signals.append(_signal(
                service, namespace, deployment, "container_restart_count", rc, cfg,
                pod_name=pod_name, container=cs.name,
            ))

    if not fault_type or not signals:
        return None
    return FaultEvent(namespace=namespace, service=service, deployment=deployment,
                      suspected_fault_type=fault_type, telemetry_window=signals)


def scrape_deployment_telemetry(k8s, namespace: str, deployment: str,
                                cfg=CONFIG) -> list[dict]:
    pod_list = k8s.list_pods_raw(namespace)
    if pod_list is None:
        return []
    signals: list[dict] = []
    for pod in pod_list.items:
        if _infer_deployment(pod) != deployment:
            continue
        service = (pod.metadata.labels or {}).get("app", deployment)
        phase = pod.status.phase if pod.status else "Unknown"
        pod_name = pod.metadata.name
        for cs in (pod.status.container_statuses or []):
            rc = cs.restart_count or 0
            signals.append(_signal(
                service, namespace, deployment, "container_restart_count", rc, cfg,
                pod_name=pod_name, container=cs.name,
            ))
            if cs.state and cs.state.waiting and cs.state.waiting.reason:
                signal_name, value, detail = _waiting_signal(
                    cs.state.waiting.reason, pod_name, cs.name, rc)
                signals.append(_signal(
                    service, namespace, deployment, signal_name, value, cfg,
                    pod_name=pod_name, container=cs.name, extra_labels=detail,
                ))
            elif not cs.ready or phase != "Running":
                signals.append(_signal(
                    service, namespace, deployment, "service_unhealthy", 1.0, cfg,
                    pod_name=pod_name,
                    container=cs.name,
                    extra_labels={"pod_phase": phase, "container_ready": bool(cs.ready)},
                ))
    return signals


def _signal(service: str, namespace: str, deployment: str,
            signal_name: str, value: Any, cfg=CONFIG, *,
            pod_name: str | None = None, container: str | None = None,
            extra_labels: dict[str, Any] | None = None) -> dict:
    labels: dict[str, Any] = {
        "system": cfg.system_identifier,
        "namespace": namespace,
        "deployment": deployment,
    }
    if pod_name:
        labels["pod_name"] = pod_name
    if container:
        labels["container"] = container
    if extra_labels:
        labels.update(extra_labels)
    return {
        "ts": _now_rfc3339_ms(),
        "tenant_id": cfg.tenant_id,
        "service": service,
        "signal_name": signal_name,
        "value": value,
        "labels": labels,
    }


def _infer_deployment(pod) -> str:
    for ref in (pod.metadata.owner_references or []):
        if ref.kind == "ReplicaSet":
            parts = ref.name.rsplit("-", 1)
            return parts[0] if len(parts) == 2 else ref.name
    return pod.metadata.name
