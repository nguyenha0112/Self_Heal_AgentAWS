from telemetry_forwarder import TelemetryForwarder


class _Cfg:
    aws_region = "ap-southeast-1"
    telemetry_buffer_enabled = True
    telemetry_queue_url = ""
    telemetry_dlq_url = ""
    telemetry_max_retries = 1
    telemetry_backoff_s = 0.0


class _AI:
    def detect(self, telemetry_window, correlation_id):
        return {
            "correlation_id": correlation_id,
            "count": len(telemetry_window),
        }


def test_inmemory_forwarder_roundtrip():
    forwarder = TelemetryForwarder(_AI(), _Cfg())
    forwarder.enqueue_detect_request(
        telemetry_window=[{
            "ts": "2026-06-30T00:00:00.000Z",
            "tenant_id": "6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
            "service": "checkout",
            "signal_name": "queue_backlog",
            "value": 15000,
            "labels": {"namespace": "tenant-a", "deployment": "checkout"},
        }],
        correlation_id="corr-1",
    )
    res = forwarder.forward_detect_once()
    assert res["correlation_id"] == "corr-1"
    assert res["count"] == 1
