# Báo Cáo Evidence Runtime Trên EKS - CDO-02

## 1. Tóm Tắt

CDO-02 đã host một ứng dụng public thật lên AWS EKS và đã thu evidence runtime để nộp trainer/gửi AI team.

Evidence này chứng minh:

- EKS cluster `cdo-eks-cluster-dev` đang chạy thật trên AWS.
- CDO đã tạo managed node group thật để có worker node chạy pod.
- Các namespace `tenant-a`, `tenant-b`, `platform` đã tồn tại trên Kubernetes.
- Ứng dụng public `podinfo` đã chạy trong namespace `tenant-a`.
- Ứng dụng có health endpoint, readiness endpoint, logs và Prometheus metrics thật.
- CDO đã thực hiện action Kubernetes thật: `rollout restart deployment/cdo-sample-api`.
- Sau restart, Kubernetes rollout thành công và pod mới thay thế pod cũ.

Đây là evidence runtime thật trên EKS, không chỉ là mock payload hoặc tài liệu thiết kế.

## 2. Làm Rõ Về "Host App"

Trong phần này có 2 loại host khác nhau, cần phân biệt rõ:

| Hạng mục | Mục đích | Có phải evidence runtime không? |
|---|---|---|
| GitHub Pages site | Trang web giải thích cho AI/trainer hiểu app demo và mapping | Không |
| Podinfo chạy trên AWS EKS | Workload thật để lấy logs, metrics, health check và rollout evidence | Có |

Link GitHub Pages chỉ là trang giới thiệu/handoff:

```text
https://nguyenha0112.github.io/cdo-podinfo-demo-site/
```

Evidence runtime chính là app `podinfo` đã được deploy lên EKS trong namespace `tenant-a`.

## 3. Evidence AWS/EKS

Thông tin cluster:

```text
Cluster Name : cdo-eks-cluster-dev
Region       : us-east-1
Version      : 1.30
Status       : ACTIVE
AWS Account  : 938145531618
```

Ban đầu EKS API endpoint là private-only nên máy local không thể `kubectl` vào cluster. Để lấy evidence demo, CDO mở public endpoint có giới hạn IP:

```text
endpointPublicAccess  = true
endpointPrivateAccess = true
publicAccessCidrs     = ["14.224.236.94/32"]
```

Điểm an toàn:

- Không mở public endpoint cho toàn internet.
- Chỉ cho phép IP workstation hiện tại bằng `/32`.
- Với demo chính thức, nên dùng VPN/bastion/private runner hoặc mở tạm IP trainer rồi đóng lại sau khi demo.

Managed node group đã tạo:

```text
Nodegroup Name : cdo-default-ng
Instance Type  : t3.medium
Capacity Type  : ON_DEMAND
Desired Size   : 1
Min Size       : 1
Max Size       : 2
Status         : ACTIVE
```

Node đang Ready:

```text
NAME                         STATUS   ROLES    AGE     VERSION                INTERNAL-IP   EXTERNAL-IP   OS-IMAGE         KERNEL-VERSION                  CONTAINER-RUNTIME
ip-10-0-2-195.ec2.internal   Ready    <none>   3m51s   v1.30.14-eks-ecaa3a6   10.0.2.195    <none>        Amazon Linux 2   5.10.245-245.983.amzn2.x86_64   containerd://1.7.29
```

## 4. Evidence Namespace Multi-Tenant

CDO đã apply 3 namespace:

```text
kubectl apply -f manifests/namespaces/platform.yaml
kubectl apply -f manifests/namespaces/tenant-a.yaml
kubectl apply -f manifests/namespaces/tenant-b.yaml
```

Kết quả:

```text
NAME       STATUS   AGE     LABELS
tenant-a   Active   2m33s   kubernetes.io/metadata.name=tenant-a,tenant_id=tenant-a
tenant-b   Active   2m31s   kubernetes.io/metadata.name=tenant-b,tenant_id=tenant-b
platform   Active   2m37s   kubernetes.io/metadata.name=platform,tenant_id=platform
```

Ý nghĩa:

- `tenant-a` là namespace chạy workload demo chính.
- `tenant-b` dùng để chứng minh boundary/safety gate không được mutate nhầm tenant.
- `platform` dành cho thành phần platform/CDO executor trong thiết kế.

## 5. Ứng Dụng Thật Đã Host Trên EKS

CDO không dùng echo container tạm bợ cho demo runtime. Workload demo là `podinfo`, một ứng dụng Kubernetes demo public.

Nguồn public:

- GitHub: https://github.com/stefanprodan/podinfo
- Docker Hub: https://hub.docker.com/r/stefanprodan/podinfo
- Image đang dùng: `ghcr.io/stefanprodan/podinfo:6.14.0`

Manifest trong repo:

```text
manifests/workloads/tenant-a-sample-app.yaml
```

Mapping cho AI:

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

Lệnh deploy:

```text
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
```

Kết quả rollout:

```text
deployment "cdo-sample-api" successfully rolled out
```

Kết quả workload:

```text
NAME                             READY   UP-TO-DATE   AVAILABLE   AGE     CONTAINERS   IMAGES                                SELECTOR
deployment.apps/cdo-sample-api   1/1     1            1           2m19s   podinfo      ghcr.io/stefanprodan/podinfo:6.14.0   app=cdo-sample-api

NAME                                  READY   STATUS    RESTARTS   AGE   IP          NODE                         NOMINATED NODE   READINESS GATES
pod/cdo-sample-api-78f74d7696-6gtql   1/1     Running   0          90s   10.0.2.89   ip-10-0-2-195.ec2.internal   <none>           <none>

NAME                     TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)           AGE     SELECTOR
service/cdo-sample-api   ClusterIP   172.20.215.165   <none>        80/TCP,9797/TCP   2m19s   app=cdo-sample-api
```

## 6. Evidence Health, Readiness, Metrics Và Logs

CDO dùng port-forward để gọi service đang chạy trong EKS:

```text
kubectl port-forward -n tenant-a svc/cdo-sample-api 9898:80 9797:9797
```

Health check:

```text
GET http://127.0.0.1:9898/healthz

{
  "status": "OK"
}
```

Readiness check:

```text
GET http://127.0.0.1:9898/readyz

{
  "status": "OK"
}
```

Prometheus metrics sample:

```text
# HELP go_goroutines Number of goroutines that currently exist.
# TYPE go_goroutines gauge
go_goroutines 9
go_info{version="go1.26.4"} 1
http_requests_total{status="200"} 35
process_cpu_seconds_total 0.05
```

Application logs:

```text
{"level":"info","ts":"2026-06-25T01:46:36.526Z","caller":"podinfo/main.go:170","msg":"Starting podinfo","version":"6.14.0","revision":"a30fa3224289a3f3e413157104dee8844e329926","port":"9898"}
{"level":"info","ts":"2026-06-25T01:46:36.527Z","caller":"http/server.go:273","msg":"Starting HTTP Server.","addr":":9898"}
```

Ý nghĩa với AI/CDO:

- `/healthz` và `/readyz` dùng để verify sau action.
- `/metrics` cung cấp telemetry format Prometheus thật.
- Logs chứng minh app đã start trong pod trên EKS.
- Các dữ liệu này có thể đưa vào flow `/v1/detect` và `/v1/verify`.

## 7. Evidence Action Self-Heal Thật

CDO đã chạy action Kubernetes thật:

```text
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
```

Kết quả:

```text
deployment.apps/cdo-sample-api restarted
deployment "cdo-sample-api" successfully rolled out
```

Trước restart:

```text
pod/cdo-sample-api-7c8f845788-g2tmj   1/1   Running   0   42s   10.0.2.250   ip-10-0-2-195.ec2.internal
```

Sau restart:

```text
pod/cdo-sample-api-78f74d7696-6gtql   1/1   Running       0   8s    10.0.2.89    ip-10-0-2-195.ec2.internal
pod/cdo-sample-api-7c8f845788-g2tmj   1/1   Terminating   0   58s   10.0.2.250   ip-10-0-2-195.ec2.internal
```

Deployment describe:

```text
Name:                   cdo-sample-api
Namespace:              tenant-a
Annotations:            deployment.kubernetes.io/revision: 2
Replicas:               1 desired | 1 updated | 1 total | 1 available | 0 unavailable
Annotations:            kubectl.kubernetes.io/restartedAt: 2026-06-25T08:46:24+07:00
Image:                  ghcr.io/stefanprodan/podinfo:6.14.0
Available               True    MinimumReplicasAvailable
Progressing             True    NewReplicaSetAvailable
OldReplicaSets:         cdo-sample-api-7c8f845788 (0/0 replicas created)
NewReplicaSet:          cdo-sample-api-78f74d7696 (1/1 replicas created)
```

Kết luận:

- Pod đã đổi từ `cdo-sample-api-7c8f845788-g2tmj` sang `cdo-sample-api-78f74d7696-6gtql`.
- Deployment revision tăng lên `2`.
- Kubernetes báo `1 available | 0 unavailable`.
- CDO đã chứng minh được action `RESTART_DEPLOYMENT` chạy thật trên EKS sandbox.

## 8. Ý Nghĩa Với Flow AI-CDO

Evidence này chứng minh được flow tích hợp mục tiêu:

```text
CDO thu telemetry/log/metric
-> POST /v1/detect
-> AI trả anomaly + confidence
-> POST /v1/decide
-> AI trả action_plan: RESTART_DEPLOYMENT
-> CDO safety gate kiểm tra tenant-a và deployment/cdo-sample-api
-> CDO execute rollout restart trên Kubernetes
-> CDO verify bằng rollout status, /healthz, /readyz, /metrics, logs
-> POST /v1/verify
```

AI nên trả target theo namespace và deployment:

```json
{
  "action": "RESTART_DEPLOYMENT",
  "target": {
    "namespace": "tenant-a",
    "deployment": "cdo-sample-api"
  }
}
```

AI không nên target theo `pod_name`, vì pod là tài nguyên thay đổi sau rollout. CDO execute an toàn ở cấp Deployment.

## 9. File Nên Gửi Cho AI Team

```text
evidence/w11-ai-contract-sync/EKS_RUNTIME_EVIDENCE_REPORT.md
evidence/w11-ai-contract-sync/topology-graph-sample.json
evidence/w11-ai-contract-sync/detect-request.json
evidence/w11-ai-contract-sync/decide-response.json
evidence/w11-ai-contract-sync/verify-request.json
```

Tin nhắn mẫu gửi AI:

```text
CDO đã host app public podinfo thật trên AWS EKS.

Runtime mapping:
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo

Evidence gồm:
- EKS node Ready
- podinfo deployment Running
- /healthz OK
- /readyz OK
- /metrics có Prometheus output
- pod logs
- rollout restart thật và rollout status thành công

Nhờ AI confirm topology graph format và trả action_plan target theo namespace + deployment.
```

## 10. Ghi Chú Vận Hành

Node group `cdo-default-ng` đang chạy `t3.medium` để phục vụ demo. Sau khi nộp evidence hoặc demo xong, nếu cần tiết kiệm chi phí thì có thể scale desired size về `0` hoặc xóa node group theo quyết định của team.
