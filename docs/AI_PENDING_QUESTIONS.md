# Câu Hỏi Còn Lại Cho AI Team - TF3 CDO-02

Tài liệu này ghi các câu hỏi còn cần AI team xác nhận sau khi CDO-02 đã đối chiếu contract AI tại commit `f0248ce667fa77cd5cbe1abc0d39ef6e81b321c9`.

## 1. Mock API Chính Thức

AI vui lòng cung cấp base URL có thể gọi được cho:

```text
POST /v1/detect
POST /v1/decide
POST /v1/verify
```

CDO cần thêm:

- Auth method.
- Required headers.
- Một ví dụ curl/Postman gọi thành công.
- Health/readiness endpoint nếu có.

## 2. Tenant ID Chính Thức

Deployment contract hiện map `cdo-2` với UUID:

```text
6c8b4b2b-4d45-4209-a1b4-4b532d56a31c
```

AI xác nhận CDO-02 có dùng UUID này cho `X-Tenant-Id` và telemetry `tenant_id` không?

## 3. Evidence W11/W12 Có Được Chấp Nhận Không?

CDO hiện đã có:

- App public `podinfo` chạy thật trên AWS EKS.
- Logs, health check, readiness check, Prometheus metrics thật.
- Action thật `RESTART_DEPLOYMENT` bằng Kubernetes rollout restart.
- Mock payload đúng contract cho `/v1/detect`, `/v1/decide`, `/v1/verify`.

AI/trainer xác nhận setup này có đủ cho W11/W12 evidence không, hay AI yêu cầu thêm một app business đầy đủ hơn?

## 4. `pattern_type=deferred`

Với `pattern_type=deferred`, AI xác nhận CDO phải đi theo GitOps/PR/commit flow và không mutate Kubernetes trực tiếp đúng không?

CDO hiểu hiện tại:

- `urgent`: CDO có thể execute Kubernetes trực tiếp sau safety gate.
- `deferred`: CDO tạo thay đổi GitOps/PR, không gọi Kubernetes API trực tiếp.

## 5. Ngưỡng Confidence

AI đề xuất ngưỡng `confidence` tối thiểu bao nhiêu để CDO được gọi `/v1/decide` và execute action?

Nếu AI không quy định, CDO sẽ để ngưỡng này configurable và mặc định escalation/manual review khi confidence thấp.

## 6. Enum `suspected_fault_type`

AI vui lòng publish danh sách giá trị hợp lệ cho:

```text
anomaly_context.suspected_fault_type
```

CDO cần danh sách này để map fault type với:

- Safety gate rule.
- Fallback runbook.
- Action candidates.

## 7. Coverage Của Mock Response

AI mock có thể trả ví dụ cho đầy đủ action enum hiện tại không?

```text
RESTART_DEPLOYMENT
PATCH_MEMORY_LIMIT
SCALE_REPLICAS
ROLLOUT_UNDO
ROTATE_SECRET
```

CDO cần biết action nào được demo thật, action nào chỉ design-only hoặc manual approval.

## 8. Policy Cho `ROTATE_SECRET`

AI có trả `ROTATE_SECRET` trong demo không?

Nếu có, AI vui lòng cung cấp:

- Required params.
- Guardrails.
- Verify policy.
- Rollback/escalation behavior.

Cho tới khi AI xác nhận rõ, CDO sẽ deny hoặc yêu cầu manual approval với `ROTATE_SECRET`.

## 9. SQS Ownership

AI xác nhận SQS có còn là interface giữa AI và CDO không?

CDO hiểu hiện tại:

- AI contract mới chưa cung cấp SQS queue ARN.
- CDO chỉ giữ SQS như optional internal telemetry buffer nếu cần.
- AI-CDO interface chính vẫn là HTTP API `/v1/detect`, `/v1/decide`, `/v1/verify`.

## 10. Topology Registry

CDO đã cung cấp graph mẫu:

```text
evidence/w11-ai-contract-sync/topology-graph-sample.json
```

Mapping chính:

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

AI xác nhận format này đủ để build dependency correlation và trả action target theo namespace/deployment chưa?

## 11. Fallback Runbook

Khi AI timeout, trả 503, vượt cost cap hoặc response không parse được, AI có cung cấp static fallback runbook không?

Nếu không, CDO sẽ tự own fallback/escalation policy và gửi AI review.

## 12. Format Action Target

AI vui lòng target Kubernetes action theo format:

```json
{
  "action": "RESTART_DEPLOYMENT",
  "target": {
    "namespace": "tenant-a",
    "deployment": "cdo-sample-api"
  }
}
```

Không target theo `pod_name`, vì pod thay đổi sau rollout. CDO execute an toàn ở cấp Deployment.
