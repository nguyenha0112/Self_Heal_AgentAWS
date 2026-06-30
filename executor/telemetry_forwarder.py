"""
SQS-backed telemetry forwarder.

Dev/local:
- không có queue URL -> dùng in-memory buffer
AWS/runtime:
- có queue URL -> enqueue telemetry_window vào SQS, worker pull rồi POST /v1/detect
"""
from __future__ import annotations

import json
import time
from typing import Any

from ai_client import AIClient
from config import CONFIG
from errors import AIBadRequest, AIError, TelemetryContractError

try:
    import boto3
    _HAS_BOTO = True
except ImportError:
    _HAS_BOTO = False


class InMemoryTelemetryBuffer:
    def __init__(self):
        self._items: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self._items.append(payload)

    def receive(self) -> dict[str, Any] | None:
        if not self._items:
            return None
        return self._items.pop(0)

    def send_dlq(self, payload: dict[str, Any]) -> None:
        self._items.append({"dlq": True, **payload})


class SQSTelemetryBuffer:
    def __init__(self, queue_url: str, dlq_url: str, cfg=CONFIG):
        self.queue_url = queue_url
        self.dlq_url = dlq_url
        self._sqs = boto3.client("sqs", region_name=cfg.aws_region)

    def send(self, payload: dict[str, Any]) -> None:
        self._sqs.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(payload))

    def receive(self) -> dict[str, Any] | None:
        resp = self._sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=1,
        )
        messages = resp.get("Messages", [])
        if not messages:
            return None
        message = messages[0]
        self._sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )
        return json.loads(message["Body"])

    def send_dlq(self, payload: dict[str, Any]) -> None:
        if not self.dlq_url:
            return
        self._sqs.send_message(QueueUrl=self.dlq_url, MessageBody=json.dumps(payload))


class TelemetryForwarder:
    def __init__(self, ai: AIClient, cfg=CONFIG):
        self.ai = ai
        self.cfg = cfg
        if cfg.telemetry_buffer_enabled and cfg.telemetry_queue_url and _HAS_BOTO:
            self.buffer = SQSTelemetryBuffer(cfg.telemetry_queue_url, cfg.telemetry_dlq_url, cfg)
        else:
            self.buffer = InMemoryTelemetryBuffer()

    def enqueue_detect_request(self, telemetry_window: list[dict], correlation_id: str) -> None:
        payload = {
            "correlation_id": correlation_id,
            "telemetry_window": telemetry_window,
        }
        self.buffer.send(payload)

    def forward_detect_once(self) -> dict[str, Any]:
        payload = self.buffer.receive()
        if payload is None:
            raise TelemetryContractError("telemetry_buffer_empty")

        correlation_id = payload["correlation_id"]
        telemetry_window = payload["telemetry_window"]
        last_err: Exception | None = None
        for attempt in range(self.cfg.telemetry_max_retries + 1):
            try:
                return self.ai.detect(telemetry_window, correlation_id)
            except AIBadRequest as e:
                self.buffer.send_dlq({
                    "reason": e.audit_reason,
                    "correlation_id": correlation_id,
                    "telemetry_window": telemetry_window,
                })
                raise
            except AIError as e:
                last_err = e
                if attempt >= self.cfg.telemetry_max_retries:
                    raise
                time.sleep(self.cfg.telemetry_backoff_s * (attempt + 1))
        if last_err:
            raise last_err
        raise TelemetryContractError("telemetry_forward_failed")
