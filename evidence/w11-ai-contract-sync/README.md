# Evidence W11 AI Contract Sync - CDO-02

Thư mục này là gói evidence để nộp trainer và gửi AI team khi tích hợp contract.

## 1. Những Gì Đã Xác Nhận

- AI repo đã được kiểm tra tại commit `f0248ce667fa77cd5cbe1abc0d39ef6e81b321c9`.
- EKS cluster `cdo-eks-cluster-dev` tồn tại thật trên AWS.
- CDO đã tạo node group `cdo-default-ng` và có node `Ready`.
- Namespace `tenant-a`, `tenant-b`, `platform` đã được apply.
- App public `podinfo` đã được host thật trên EKS trong namespace `tenant-a`.
- CDO đã lấy được health check, readiness check, Prometheus metrics và pod logs.
- CDO đã chạy action thật `kubectl rollout restart deployment/cdo-sample-api -n tenant-a`.
- Boundary hiện tại: AI decide, CDO validate/execute/verify/audit.
- `DELETE_POD` không còn nằm trong allow-list action hiện tại.
- SQS chỉ là optional internal buffer của CDO nếu AI chưa cung cấp queue ARN/interface.

## 2. Làm Rõ Về Link Web Và App Trên EKS

Link web GitHub Pages chỉ dùng để giải thích/handoff cho người đọc:

```text
https://nguyenha0112.github.io/cdo-podinfo-demo-site/
```

Link này không phải runtime evidence chính.

Runtime evidence chính là app `podinfo` đã chạy thật trên AWS EKS:

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

## 3. File Evidence Quan Trọng

- `EKS_RUNTIME_EVIDENCE_REPORT.md`: báo cáo chính, đọc file này trước khi nộp trainer.
- `topology-graph-sample.json`: graph mẫu và mapping `service -> namespace -> deployment` cho AI.
- `detect-request.json`: payload mẫu CDO gửi `/v1/detect`.
- `decide-response.json`: response mẫu AI trả `/v1/decide`.
- `verify-request.json`: payload mẫu CDO gửi `/v1/verify`.
- `safety-gate-result.txt`: quyết định pass/deny của safety gate.
- `kubectl-before-after.txt`: lệnh capture before/after rollout.
- `ai-latest-commit.txt`: commit AI contract đã đối chiếu.
- `cdo-eks-output.txt`: thông tin hạ tầng EKS.

## 4. AI Team Cần Cung Cấp Thêm

1. Base URL mock API cho:
   - `POST /v1/detect`
   - `POST /v1/decide`
   - `POST /v1/verify`
2. Auth method và sample headers để CDO gọi API.
3. Xác nhận tenant UUID chính thức của CDO-02 là `6c8b4b2b-4d45-4209-a1b4-4b532d56a31c`.
4. Danh sách `suspected_fault_type` hợp lệ.
5. Xác nhận `pattern_type=deferred` có bắt buộc đi qua GitOps/PR thay vì mutate Kubernetes trực tiếp không.
6. Xác nhận mock response có cover các action: `RESTART_DEPLOYMENT`, `PATCH_MEMORY_LIMIT`, `SCALE_REPLICAS`, `ROLLOUT_UNDO`, `ROTATE_SECRET`.
7. Xác nhận graph `topology-graph-sample.json` đủ để AI map dependency và trả target theo namespace/deployment.

## 5. Lệnh Demo Runtime

Khi cần chạy lại demo:

```powershell
kubectl get nodes -o wide
kubectl get ns tenant-a tenant-b platform --show-labels
kubectl get deploy,pod,svc -n tenant-a -o wide
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 9797:9797
curl http://127.0.0.1:9898/healthz
curl http://127.0.0.1:9898/readyz
curl http://127.0.0.1:9898/metrics
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
kubectl logs -n tenant-a deployment/cdo-sample-api --tail=30
```

## 6. Kết Luận

CDO-02 đã có evidence runtime thật trên AWS EKS, gồm workload thật, logs thật, metrics thật và action restart thật. Gói evidence này đủ để chứng minh với trainer rằng phần CDO không chỉ dừng ở mock contract mà đã có Kubernetes execution path hoạt động.
