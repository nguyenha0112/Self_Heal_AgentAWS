from telemetry_contract import normalize_window

TENANT = "6c8b4b2b-4d45-4209-a1b4-4b532d56a31c"


def test_normalize_alias_and_scrub_pii():
    raw = [{
        "service": "checkout",
        "signal_name": "error_rate",
        "value": "user=test@example.com password=secret",
        "labels": {"deployment": "checkout", "namespace": "tenant-a"},
    }]
    window = normalize_window(raw, tenant_id=TENANT)
    assert window[0]["signal_name"] == "service_error_rate"
    assert "[REDACTED_EMAIL]" in window[0]["value"]
    assert "[REDACTED]" in window[0]["value"]


def test_preserves_valid_contract_point():
    raw = [{
        "ts": "2026-06-30T00:00:00.000Z",
        "tenant_id": TENANT,
        "service": "checkout",
        "signal_name": "queue_backlog",
        "value": 15000,
        "labels": {"system": "K8S_NATIVE", "namespace": "tenant-a", "deployment": "checkout"},
    }]
    window = normalize_window(raw, tenant_id=TENANT)
    assert window[0]["signal_name"] == "queue_backlog"
    assert window[0]["value"] == 15000
