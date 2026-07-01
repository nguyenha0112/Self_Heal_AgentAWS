from types import SimpleNamespace

from ai_client import AIClient
from models import AnomalyContext, DetectResponse
from signal_registry import CDO_TO_AI_FAULT_TYPE, to_ai_fault_type


def test_detect_response_accepts_ai_engine_evidence_fields():
    response = DetectResponse.from_dict({
        "anomaly_detected": True,
        "severity": 0.8,
        "confidence": 0.9,
        "reasoning": "rca",
        "correlation_id": "corr-1",
        "anomaly_context": {
            "target_service": "checkout-svc",
            "suspected_fault_type": "mem",
            "system": "E-COMMERCE",
        },
        "service_top_k": ["checkout-svc", "orders-svc"],
        "llm_fault_rank_evidence": {"bocpd_input_summary": {"anomaly_index": 12}},
    })

    assert response.service_top_k == ["checkout-svc", "orders-svc"]
    assert response.detect_evidence()["bocpd_input_summary"]["anomaly_index"] == 12


def test_cdo_fault_type_mapping_table():
    assert CDO_TO_AI_FAULT_TYPE["OOM_KILL"] == "mem"
    assert CDO_TO_AI_FAULT_TYPE["LATENCY_SPIKE"] == "delay"
    assert to_ai_fault_type("mem") == "mem"


def test_decide_maps_cdo_fault_type_before_post():
    posted = {}

    class _Resp:
        status_code = 200
        headers = {}

        @staticmethod
        def json():
            return {
                "matched_runbook": "MemoryRecoveryRunbook",
                "pattern_type": "urgent",
                "action_plan": [],
                "blast_radius_config": {
                    "max_pod_impact_pct": 25,
                    "circuit_breaker_error_rate": 0.2,
                    "allowed_namespaces": ["tenant-a"],
                },
                "verify_policy": {"window_seconds": 30, "success_conditions": []},
                "correlation_id": "11111111-1111-4111-8111-111111111111",
                "idempotency_key": "22222222-2222-4222-8222-222222222222",
                "dry_run_mode": True,
            }

    class _Session:
        @staticmethod
        def post(url, json, headers, timeout):
            posted["url"] = url
            posted["json"] = json
            posted["headers"] = headers
            posted["timeout"] = timeout
            return _Resp()

    cfg = SimpleNamespace(
        ai_base_url="http://ai.local:8080",
        ai_timeout_decide_s=5.0,
        dry_run_mode=True,
        tenant_id="33333333-3333-4333-8333-333333333333",
        http_429_max_retries=0,
        http_500_max_retries=0,
        http_500_backoff_s=(),
    )
    client = AIClient(cfg)
    client._session = _Session()

    client.decide(
        AnomalyContext(
            target_service="checkout-svc",
            suspected_fault_type="OOM_KILL",
            system="E-COMMERCE",
            namespace="tenant-a",
        ),
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        detect_evidence={"service_top_k": ["checkout-svc"]},
    )

    assert posted["url"] == "http://ai.local:8080/v1/decide"
    assert posted["json"]["anomaly_context"]["suspected_fault_type"] == "mem"
    assert posted["json"]["detect_evidence"]["service_top_k"] == ["checkout-svc"]
