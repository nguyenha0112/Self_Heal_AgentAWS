# Monitoring Evidence Checklist

## Cần lưu vào pack evidence

- `kubectl get pods -n monitoring`
- `kubectl get servicemonitor -n monitoring`
- `kubectl get prometheusrule -n monitoring`
- `kubectl get configmap grafana-dashboard-self-heal -n monitoring -o yaml`
- screenshot dashboard `CDO Self-Heal Overview`
- screenshot alert firing hoặc panel restart/availability đổi trạng thái khi inject lỗi
- `kubectl logs deploy/cdo-executor -n self-heal-system --tail=200`
- `aws s3 ls s3://<audit-bucket>/audit/<tenant-id>/`
- 1 file audit JSON tải từ S3 theo `correlation_id`

## Kết quả mong đợi

- Grafana có dashboard `CDO Self-Heal Overview`
- Prometheus scrape được metrics của tenant workloads
- AI engine có thể scrape `/metrics` ngay khi image thật được deploy
- Rule cảnh báo phát hiện được unavailable replicas, restart spike, OOMKilled
- Audit evidence khớp với sự kiện quan sát được trên dashboard
