# Runbook - Redeploy After `terraform destroy`

## Mục tiêu

Khôi phục lại toàn bộ CDO self-heal sandbox sau khi đã `terraform destroy`, giữ nguyên phần AI image là biến handoff để mai team AI gửi image/tag rồi mới apply bước cuối.

## Điều kiện cần trước khi chạy lại

- AWS CLI đang trỏ đúng account/region của sandbox.
- Đã cài `terraform`, `kubectl`, `helm`, `docker`.
- Có quyền `eks`, `iam`, `s3`, `dynamodb`, `ecr`, `cloudwatch`.
- Nếu dùng AI image thật: đã có `ECR URI + immutable tag` từ team AI.

## 1. Khôi phục hạ tầng AWS

```powershell
cd C:\Users\Admin\Desktop\W-12LAB\TF3-Self-Heal-Agent-AWS\infra\envs\dev
terraform init
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
terraform apply
```

Ghi lại các output sau:

```powershell
terraform output
terraform output -raw ecr_executor_url
terraform output -raw audit_bucket_name
terraform output -raw executor_role_arn
terraform output -raw telemetry_queue_url
terraform output -raw telemetry_dlq_url
```

## 2. Cập nhật kubeconfig và kiểm tra cluster

```powershell
aws eks update-kubeconfig --name cdo-eks-cluster-dev --region ap-southeast-1
kubectl get nodes
kubectl get ns
```

Kỳ vọng:

- Có namespace `tenant-a`, `tenant-b`, `self-heal-system`, `monitoring`, `argocd`, `kyverno`.
- Node ở trạng thái `Ready`.

## 3. Build và push executor image

```powershell
$EcrBase = "938145531618.dkr.ecr.ap-southeast-1.amazonaws.com"
$ExecutorImage = "$EcrBase/cdo-executor:v1"
$Password = aws ecr get-login-password --region ap-southeast-1
docker login --username AWS --password $Password $EcrBase
docker build --platform linux/amd64 -t $ExecutorImage .\executor
docker push $ExecutorImage
```

## 4. Cập nhật manifest runtime

Sửa các placeholder trong [k8s/03-executor.yaml](/C:/Users/Admin/Desktop/W-12LAB/TF3-Self-Heal-Agent-AWS/k8s/03-executor.yaml) nếu cần:

- `REPLACE_WITH_ECR_URL:latest` -> ECR executor image thật
- `REPLACE_WITH_AUDIT_BUCKET` -> `terraform output -raw audit_bucket_name`

Nếu dùng manifest wrapper thay vì `k8s/03-executor.yaml`, cập nhật [manifests/executor/configmap.yaml](/C:/Users/Admin/Desktop/W-12LAB/TF3-Self-Heal-Agent-AWS/manifests/executor/configmap.yaml) bằng:

- `CDO_AUDIT_BUCKET`
- `CDO_IDEMPOTENCY_TABLE`
- `AWS_REGION`
- `CDO_TELEMETRY_QUEUE_URL`
- `CDO_TELEMETRY_DLQ_URL`

## 5. Apply nền tảng và workload

```powershell
kubectl apply -f .\k8s\00-namespaces.yaml
kubectl apply -f .\k8s\01-rbac.yaml
kubectl apply -f .\k8s\04-workloads.yaml
kubectl apply -f .\manifests\kyverno\policies\
kubectl apply -f .\manifests\networkpolicies\
kubectl apply -f .\manifests\monitoring\
kubectl apply -f .\k8s\03-executor.yaml
```

## 6. Apply AI engine khi có image thật

File chờ handoff: [manifests/ai-engine/deployment.yaml.template](/C:/Users/Admin/Desktop/W-12LAB/TF3-Self-Heal-Agent-AWS/manifests/ai-engine/deployment.yaml.template)

Việc cần làm:

1. Copy file template thành `deployment.yaml`
2. Điền `<AI_ENGINE_IMAGE>` bằng image team AI gửi
3. Apply:

```powershell
kubectl apply -f .\manifests\ai-engine\deployment.yaml
kubectl rollout status deploy/ai-engine -n self-heal-system
```

## 7. Verify monitoring và Grafana

```powershell
kubectl get pods -n monitoring
kubectl get servicemonitor -n monitoring
kubectl get configmap grafana-dashboard-self-heal -n monitoring -o name
kubectl port-forward svc/kube-prometheus-stack-grafana -n monitoring 3000:80
```

Kỳ vọng:

- Lấy user/password từ secret Kubernetes thay vì dùng credential tĩnh:

```powershell
kubectl get secret grafana-admin-credentials -n monitoring -o jsonpath="{.data.admin-user}" | % { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
kubectl get secret grafana-admin-credentials -n monitoring -o jsonpath="{.data.admin-password}" | % { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

- Grafana login được bằng credential đọc từ secret `grafana-admin-credentials`
- Có dashboard `CDO Self-Heal Overview`
- Prometheus scrape được `checkout-svc`, `notification-svc`, và `ai-engine` khi AI pod đã lên

## 8. Verify self-heal end-to-end

```powershell
kubectl logs deploy/cdo-executor -n self-heal-system -f
kubectl set resources deploy/cdo-sample-api -n tenant-a -c podinfo --limits=memory=8Mi --requests=memory=8Mi
kubectl get deploy cdo-sample-api -n tenant-a -o jsonpath='{..limits.memory}'
```

Kỳ vọng:

- Executor log thấy detect -> decide -> safety -> execute -> verify
- Deployment được patch lại memory nếu AI trả action phù hợp
- Audit object xuất hiện trong S3 bucket audit

## 9. Thu evidence sau khi verify

Lưu kết quả vào:

- [evidence/w12-alignment/AI_SOURCE_SYNC.md](/C:/Users/Admin/Desktop/W-12LAB/TF3-Self-Heal-Agent-AWS/evidence/w12-alignment/AI_SOURCE_SYNC.md)
- [evidence/w12-monitoring/MONITORING_EVIDENCE_CHECKLIST.md](/C:/Users/Admin/Desktop/W-12LAB/TF3-Self-Heal-Agent-AWS/evidence/w12-monitoring/MONITORING_EVIDENCE_CHECKLIST.md)

Artifacts nên chụp/lưu:

- `kubectl get pods -A`
- `kubectl get servicemonitor -n monitoring`
- screenshot Grafana dashboard
- `aws s3 ls s3://<audit-bucket>/audit/<tenant-id>/`
- một sample audit JSON theo `correlation_id`

## 10. Destroy sau khi chốt xong

Nếu đã xem Grafana, đã chụp evidence và không cần giữ cluster nữa thì teardown theo đúng thứ tự này:

```powershell
cd C:\Users\Admin\Desktop\W-12LAB\TF3-Self-Heal-Agent-AWS\infra\envs\dev
terraform destroy -auto-approve
```

Sau destroy kiểm tra lại:

```powershell
aws eks list-clusters --region ap-southeast-1
```

Kỳ vọng:

- cluster `cdo-eks-cluster-dev` không còn trong danh sách
- các namespace/pod trong cluster cũ không còn truy cập được nữa

Lưu ý:

- bucket audit dùng Object Lock nên nếu có object audit bị giữ retention, destroy có thể còn để lại phần bucket/object cho tới khi xử lý retention phù hợp
- không chạy `terraform destroy` khi vẫn còn cần đối chiếu dashboard hoặc lấy evidence
