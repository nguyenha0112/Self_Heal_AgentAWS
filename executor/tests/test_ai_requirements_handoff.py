import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REQ_DIR = REPO_ROOT / "docs" / "handoff" / "ai-requirements"
HANDOFF_DIR = REPO_ROOT / "docs" / "handoff" / "ai-inputs"
WORKLOAD_A = REPO_ROOT / "manifests" / "workloads" / "tenant-a-sample-app.yaml"
WORKLOAD_B = REPO_ROOT / "manifests" / "workloads" / "tenant-b-sample-app.yaml"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_service_registry_matches_deployed_workloads():
    registry = _load_json(REQ_DIR / "service_registry_CDO02.json")
    services = {item["service"]: item for item in registry["services"]}

    assert "checkout-svc" in services
    assert services["checkout-svc"]["namespace"] == "tenant-a"
    assert services["checkout-svc"]["deployment"] == "cdo-sample-api"
    assert "selfheal.ai/service: checkout-svc" in WORKLOAD_A.read_text(encoding="utf-8")
    assert "name: cdo-sample-api" in WORKLOAD_A.read_text(encoding="utf-8")

    assert "notification-svc" in services
    assert services["notification-svc"]["namespace"] == "tenant-b"
    assert services["notification-svc"]["deployment"] == "notification-service"
    assert "name: notification-service" in WORKLOAD_B.read_text(encoding="utf-8")


def test_tenant_profiles_are_namespace_safe():
    tenant_a = _load_json(REQ_DIR / "platform_profile_CDO02_tenant_a.json")
    tenant_b = _load_json(REQ_DIR / "platform_profile_CDO02_tenant_b.json")

    assert tenant_a["allowed_namespaces"] == ["tenant-a"]
    assert tenant_a["runbooks"]["ServiceStuckRestartRunbook"]["action_plan"][0]["params"]["namespace"] == "tenant-a"
    assert tenant_a["runbooks"]["OOMPatchMemoryRunbook"]["action_plan"][0]["target"] == "deployment/cdo-sample-api"

    assert tenant_b["allowed_namespaces"] == ["tenant-b"]
    assert tenant_b["runbooks"]["ServiceStuckRestartRunbook"]["action_plan"][0]["params"]["namespace"] == "tenant-b"
    assert tenant_b["runbooks"]["OOMPatchMemoryRunbook"]["action_plan"][0]["target"] == "deployment/notification-service"


def test_handoff_payloads_use_known_service_and_deployment_mapping():
    registry = _load_json(REQ_DIR / "service_registry_CDO02.json")
    known = {}
    for item in registry["services"]:
        known[item["service"]] = item
        for alias in item["aliases"]:
            known[alias] = item
        known[item["deployment"]] = item

    detect_a = _load_json(HANDOFF_DIR / "01_detect_request_oom_kill_tenant_a.json")
    decide_b = _load_json(HANDOFF_DIR / "04_decide_request_scale_capacity_tenant_b.json")
    verify_b = _load_json(HANDOFF_DIR / "06_verify_request_restart_tenant_b.json")

    first_point = detect_a["telemetry_window"][0]
    mapped_a = known[first_point["service"]]
    assert mapped_a["namespace"] == first_point["labels"]["namespace"]
    assert mapped_a["deployment"] == first_point["labels"]["deployment"]

    anomaly_b = decide_b["anomaly_context"]
    mapped_b = known[anomaly_b["target_service"]]
    assert mapped_b["namespace"] == anomaly_b["namespace"]
    assert mapped_b["deployment"] == anomaly_b["deployment"]

    verify_target = verify_b["action_executed"]["target"].split("/", 1)[1]
    mapped_verify = known[verify_target]
    assert mapped_verify["deployment"] == verify_target
