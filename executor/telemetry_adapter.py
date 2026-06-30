"""
Telemetry adapter: đọc raw telemetry rồi normalize/validate/map/scrub theo contract.
"""
from __future__ import annotations

from config import CONFIG
from telemetry_contract import normalize_window


class TelemetryAdapter:
    def __init__(self, cfg=CONFIG):
        self.cfg = cfg

    def build_window(self, raw_points: list[dict]) -> list[dict]:
        return normalize_window(raw_points, tenant_id=self.cfg.tenant_id)
