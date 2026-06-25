# Workload Demo CDO-02

CDO-02 dùng `stefanprodan/podinfo` làm ứng dụng public để demo luồng self-heal W11/W12.

## Vì Sao Chọn Podinfo?

- Đây là app public thật, không phải echo container tạm bợ.
- Có endpoint liveness/readiness: `/healthz`, `/readyz`.
- Có Prometheus metrics trên port `9797`.
- Có HTTP behavior và logs để dùng làm telemetry evidence.
- Nhẹ, phù hợp để chạy trên EKS sandbox.

Nguồn public:

```text
https://github.com/stefanprodan/podinfo
https://hub.docker.com/r/stefanprodan/podinfo
```

Image đang dùng:

```text
ghcr.io/stefanprodan/podinfo:6.14.0
```

## Mapping Chính

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

AI nên trả action target theo `namespace` + `deployment`, không target theo `pod_name`.

## Lệnh Kiểm Tra

```powershell
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
kubectl get deploy,pod,svc -n tenant-a -o wide
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 9797:9797
curl http://127.0.0.1:9898/healthz
curl http://127.0.0.1:9898/readyz
curl http://127.0.0.1:9898/metrics
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
```
