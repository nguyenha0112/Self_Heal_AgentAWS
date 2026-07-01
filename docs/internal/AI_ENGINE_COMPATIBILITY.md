# AI Engine Compatibility Note

This repo was checked against `AIops-g4/Capstone-Phase-2-Code/tree/main/tf-3/ai`.

## Summary

- The AI repo exposes `/v1/detect`, `/v1/decide`, and `/v1/verify`.
- Our executor and mock AI flow follow the same detect-decide-verify contract shape.
- The AI contract expects idempotency headers and request fields that match the current CDO flow.
- The AI deployment model is still wrapper-based in this repo: CDO deploys the AI image, but does not own AI business logic.

## Compatibility Notes

- `executor/mock_ai_server.py` already returns payloads compatible with the detect/decide/verify loop used by the executor.
- `manifests/ai-engine/deployment.yaml.template` remains the handoff point for the real AI image.
- The current repo keeps observability on the CDO side and does not enable Alertmanager.

## Observability Direction

- `image-1.png` is treated as the latest target architecture.
- The implementation direction in this repo is:
  - Prometheus
  - Grafana
  - OpenTelemetry Collector
- Alertmanager is intentionally disabled in the current Terraform-based deployment.
