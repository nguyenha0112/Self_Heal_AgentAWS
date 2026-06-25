# CDO-02 EKS Runtime Evidence Report

## 1. Executive Summary

CDO-02 has deployed a real public Kubernetes demo application on AWS EKS and captured runtime evidence for the AI integration handoff.

This evidence proves:

- The EKS cluster is reachable from the CDO workstation after enabling a restricted public endpoint.
- A real managed node group is running.
- Namespaces `tenant-a`, `tenant-b`, and `platform` exist.
- The public app `podinfo` is running in `tenant-a`.
- The app exposes real health, readiness, logs, and Prometheus metrics.
- CDO executed a real Kubernetes `rollout restart` action and verified the rollout.

This is not only a mock JSON evidence pack. The workload is running on AWS EKS.

## 2. AWS/EKS Infrastructure Evidence

Cluster:

```text
Cluster Name : cdo-eks-cluster-dev
Region       : us-east-1
Version      : 1.30
Status       : ACTIVE
AWS Account  : 938145531618
```

EKS endpoint access was updated for the demo:

```text
endpointPublicAccess  = true
endpointPrivateAccess = true
publicAccessCidrs     = ["14.224.236.94/32"]
```

Reason:

- The cluster was originally private-only.
- Local `kubectl` could not reach the Kubernetes API.
- CDO temporarily allowed the current workstation IP only, using `/32`, instead of opening the endpoint broadly.

Managed node group created:

```text
Nodegroup Name : cdo-default-ng
Instance Type  : t3.medium
Capacity Type  : ON_DEMAND
Desired Size   : 1
Min Size       : 1
Max Size       : 2
Status         : ACTIVE
```

Node evidence:

```text
NAME                         STATUS   ROLES    AGE     VERSION                INTERNAL-IP   EXTERNAL-IP   OS-IMAGE         KERNEL-VERSION                  CONTAINER-RUNTIME
ip-10-0-2-195.ec2.internal   Ready    <none>   3m51s   v1.30.14-eks-ecaa3a6   10.0.2.195    <none>        Amazon Linux 2   5.10.245-245.983.amzn2.x86_64   containerd://1.7.29
```

## 3. Kubernetes Namespace Evidence

CDO applied the required namespaces for multi-tenant isolation:

```text
kubectl apply -f manifests/namespaces/platform.yaml
kubectl apply -f manifests/namespaces/tenant-a.yaml
kubectl apply -f manifests/namespaces/tenant-b.yaml
```

Observed namespaces:

```text
NAME       STATUS   AGE     LABELS
tenant-a   Active   2m33s   kubernetes.io/metadata.name=tenant-a,tenant_id=tenant-a
tenant-b   Active   2m31s   kubernetes.io/metadata.name=tenant-b,tenant_id=tenant-b
platform   Active   2m37s   kubernetes.io/metadata.name=platform,tenant_id=platform
```

## 4. Real App Hosted On EKS

CDO does not use a temporary echo container for the live demo. The hosted app is `podinfo`, a public Kubernetes demo microservice.

Public references:

- GitHub: https://github.com/stefanprodan/podinfo
- Docker Hub: https://hub.docker.com/r/stefanprodan/podinfo
- Image used by CDO: `ghcr.io/stefanprodan/podinfo:6.14.0`

CDO manifest:

```text
manifests/workloads/tenant-a-sample-app.yaml
```

Topology mapping for AI:

```text
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo
```

Deployment command:

```text
kubectl apply -f manifests/workloads/tenant-a-sample-app.yaml
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
```

Rollout result:

```text
deployment "cdo-sample-api" successfully rolled out
```

Runtime workload evidence:

```text
NAME                             READY   UP-TO-DATE   AVAILABLE   AGE     CONTAINERS   IMAGES                                SELECTOR
deployment.apps/cdo-sample-api   1/1     1            1           2m19s   podinfo      ghcr.io/stefanprodan/podinfo:6.14.0   app=cdo-sample-api

NAME                                  READY   STATUS    RESTARTS   AGE   IP          NODE                         NOMINATED NODE   READINESS GATES
pod/cdo-sample-api-78f74d7696-6gtql   1/1     Running   0          90s   10.0.2.89   ip-10-0-2-195.ec2.internal   <none>           <none>

NAME                     TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)           AGE     SELECTOR
service/cdo-sample-api   ClusterIP   172.20.215.165   <none>        80/TCP,9797/TCP   2m19s   app=cdo-sample-api
```

## 5. Health, Readiness, Metrics, And Logs Evidence

CDO used port-forward to query the live EKS service:

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

Why this matters for AI:

- `/healthz` and `/readyz` can be used as post-action verification signals.
- `/metrics` provides real Prometheus-format runtime metrics.
- Logs prove the application started inside the EKS pod.
- These signals can populate `/v1/detect` and `/v1/verify` test payloads.

## 6. Real Kubernetes Self-Heal Action Evidence

CDO executed a real Kubernetes restart action:

```text
kubectl rollout restart deployment/cdo-sample-api -n tenant-a
kubectl rollout status deployment/cdo-sample-api -n tenant-a --timeout=180s
```

Action result:

```text
deployment.apps/cdo-sample-api restarted
deployment "cdo-sample-api" successfully rolled out
```

Before restart:

```text
pod/cdo-sample-api-7c8f845788-g2tmj   1/1   Running   0   42s   10.0.2.250   ip-10-0-2-195.ec2.internal
```

After restart:

```text
pod/cdo-sample-api-78f74d7696-6gtql   1/1   Running       0   8s    10.0.2.89    ip-10-0-2-195.ec2.internal
pod/cdo-sample-api-7c8f845788-g2tmj   1/1   Terminating   0   58s   10.0.2.250   ip-10-0-2-195.ec2.internal
```

Deployment describe evidence:

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

Interpretation:

- The pod name changed from `cdo-sample-api-7c8f845788-g2tmj` to `cdo-sample-api-78f74d7696-6gtql`.
- The deployment revision increased to `2`.
- Kubernetes reports `1 available | 0 unavailable`.
- This proves CDO can execute the safe action `RESTART_DEPLOYMENT` on the EKS sandbox.

## 7. AI Integration Meaning

This runtime evidence supports the following AI-CDO contract flow:

```text
CDO telemetry/log/metric collection
-> POST /v1/detect
-> AI returns anomaly + confidence
-> POST /v1/decide
-> AI returns action_plan: RESTART_DEPLOYMENT
-> CDO safety gate validates tenant-a and deployment/cdo-sample-api
-> CDO executes Kubernetes rollout restart
-> CDO checks rollout status, healthz, readyz, metrics, logs
-> POST /v1/verify
```

AI should target the action by namespace and deployment:

```json
{
  "action": "RESTART_DEPLOYMENT",
  "target": {
    "namespace": "tenant-a",
    "deployment": "cdo-sample-api"
  }
}
```

AI should not target an individual `pod_name`, because CDO controls safe restart at Deployment level.

## 8. What To Send AI Team

Send AI team these files:

```text
evidence/w11-ai-contract-sync/EKS_RUNTIME_EVIDENCE_REPORT.md
evidence/w11-ai-contract-sync/topology-graph-sample.json
evidence/w11-ai-contract-sync/detect-request.json
evidence/w11-ai-contract-sync/decide-response.json
evidence/w11-ai-contract-sync/verify-request.json
```

Short message:

```text
CDO has hosted a real public app on AWS EKS using podinfo.

Runtime mapping:
checkout-svc -> tenant-a -> deployment/cdo-sample-api -> container/podinfo

Evidence includes:
- EKS node Ready
- podinfo deployment Running
- /healthz OK
- /readyz OK
- /metrics Prometheus output
- pod logs
- real rollout restart and successful rollout status

Please confirm the topology graph format and return AI action_plan targets by namespace + deployment.
```

## 9. Current Caveat

The EKS public endpoint was opened only for the current workstation IP:

```text
14.224.236.94/32
```

For a final demo environment, CDO should either:

- keep endpoint private and run commands from VPN/bastion/private runner, or
- temporarily allow the trainer/demo operator IP with `/32`, then close it after evidence capture.
