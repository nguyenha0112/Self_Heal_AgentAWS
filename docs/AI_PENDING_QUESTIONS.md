# Pending Questions For AI Team - TF3 CDO-02

These questions remain after aligning CDO-02 docs with the latest AI contracts.

1. Tenant ID
   Confirm the official UUID for CDO-02. Current deployment contract maps `cdo-2` to `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`; should CDO-02 use this value in `X-Tenant-Id` and telemetry `tenant_id`?

2. AI skeleton endpoint
   When will the stable stub endpoint be available for CDO integration testing? Please confirm reachable URL, health/readiness URLs, auth setup, and whether `https://ai-engine.tf-3.internal/` is already routable from the CDO environment.

3. Confidence threshold
   What minimum `/v1/detect` confidence should CDO use before calling `/v1/decide` and executing an action? If AI does not prescribe it, CDO-02 will make it configurable and default to manual escalation below threshold.

4. `DELETE_POD` policy
   AI API contract still allows `DELETE_POD`. Will AI return this action in W12 demo scenarios? Should CDO deny it by default, require manual approval, or support a narrow safe path?

5. `ROTATE_SECRET` policy
   Will AI return `ROTATE_SECRET` during demo, and what guardrails/params should CDO enforce beyond `secret_name` and namespace checks?

6. `suspected_fault_type` enum
   Please publish the possible `anomaly_context.suspected_fault_type` values. CDO needs an allow-list to map fault types to safety gates and fallback runbooks.

7. SQS ownership
   Earlier docs implied telemetry via SQS, while the latest telemetry contract describes normalized payloads and OTel/Prometheus/Fluentd sources but does not provide an SQS queue ARN. Is SQS still part of the AI-CDO interface, or can CDO keep SQS only as an internal buffer?

8. Offline simulation evidence
   Is RE2/RE3 Mock Mode enough evidence for W12, or should CDO-02 add at least one live Kubernetes sandbox action scenario?

9. 503 fallback runbook
   Does AI provide a static fallback runbook for AI timeout/503, or should CDO-02 own the fallback/escalation policy and request AI review?

10. Namespace registry
   For `/v1/decide.blast_radius_config.allowed_namespaces`, does AI generate namespaces from telemetry labels, or does CDO need to register tenant namespace mappings with AI beforehand?

