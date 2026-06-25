# Pending Questions For AI Team - TF3 CDO-02

These questions remain after aligning CDO-02 docs with AI repo commit `f0248ce667fa77cd5cbe1abc0d39ef6e81b321c9`.

1. Hosted mock API
   Please provide the reachable base URL for `POST /v1/detect`, `POST /v1/decide`, and `POST /v1/verify`, including auth method, required headers, and one successful curl/Postman example.

2. Tenant ID
   Confirm the official UUID for CDO-02. Current deployment contract maps `cdo-2` to `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`; should CDO-02 use this value in `X-Tenant-Id` and telemetry `tenant_id`?

3. W11/W12 evidence acceptance
   Can W11/W12 accept AI mock API integration plus one real CDO Kubernetes sandbox action, or does AI require CDO to host a full app that continuously emits live telemetry?

4. `pattern_type=deferred`
   Confirm that `deferred` actions must use GitOps/PR/commit flow and must not directly mutate the Kubernetes cluster from the CDO executor.

5. Confidence threshold
   What minimum `/v1/detect` confidence should CDO use before calling `/v1/decide` and executing an action? If AI does not prescribe it, CDO-02 will default to configurable threshold plus manual escalation below threshold.

6. `suspected_fault_type` enum
   Please publish the possible `anomaly_context.suspected_fault_type` values and map each value to expected action candidates.

7. Mock response coverage
   Can the AI mock return examples for all current actions: `RESTART_DEPLOYMENT`, `PATCH_MEMORY_LIMIT`, `SCALE_REPLICAS`, `ROLLOUT_UNDO`, and `ROTATE_SECRET`?

8. `ROTATE_SECRET` policy
   Will AI return `ROTATE_SECRET` during demo, and what guardrails/params should CDO enforce beyond `secret_name` and namespace checks? Until confirmed, CDO will deny or require manual approval.

9. SQS ownership
   Confirm that SQS is not part of the AI-CDO interface unless AI publishes a queue ARN and access policy. CDO will keep SQS only as an optional internal telemetry buffer.

10. Topology registry
   For `/v1/decide.blast_radius_config.allowed_namespaces`, does AI infer namespaces from telemetry labels, or does CDO need to register service-to-namespace-to-deployment mappings before testing?

11. Fallback runbook
   Does AI provide static fallback runbooks for timeout/503/cost-cap cases, or should CDO-02 own fallback/escalation policy and send it to AI for review?

12. Topology graph sample
   CDO provides `evidence/w11-ai-contract-sync/topology-graph-sample.json`. Please confirm this graph format is enough for AI to build dependency correlation and return namespace/deployment targets.
