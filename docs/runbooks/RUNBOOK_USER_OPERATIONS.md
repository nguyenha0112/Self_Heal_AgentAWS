# Runbook User Operations

## 1. File gửi cho team AI

Chỉ gửi thư mục này:

- `docs/handoff/ai-inputs/`

Ý nghĩa:

- chứa đúng 6 JSON mẫu CDO gửi sang AI
- có `README.md` mô tả header và mục đích từng file

Không cần gửi `evidence` hay `runbook` nội bộ cho AI team.

## 2. File nội bộ của bạn

Giữ lại các file này cho vận hành và báo cáo:

- `evidence/w12-runtime/`
- `evidence/w12-alignment/`
- `evidence/w12-monitoring/`
- `docs/runbooks/RUNBOOK_REDEPLOY_AFTER_DESTROY.md`
- `docs/runbooks/RUNBOOK_USER_OPERATIONS.md`

## 3. Kiểm tra nhanh phần CDO đã đủ chưa

Xem file:

- `evidence/w12-runtime/CDO_STATUS_CHECK.md`

Kết luận hiện tại:

- đủ phần CDO nếu bỏ qua build image
- đủ monitoring/Grafana/dashboard
- đủ handoff payload cho AI

## 4. Sau khi team AI gửi image thật

Làm riêng bước này:

1. copy `manifests/ai-engine/deployment.yaml.template` thành `deployment.yaml`
2. thay `<AI_ENGINE_IMAGE>`
3. apply manifest AI

## 5. Sau khi cần dựng lại môi trường

Dùng:

- `docs/runbooks/RUNBOOK_REDEPLOY_AFTER_DESTROY.md`

## 6. Sau khi chốt evidence thì teardown

Thứ tự:

1. capture evidence
2. kiểm tra file handoff và runbook đã có
3. chạy `terraform destroy` ở `infra/envs/dev`

Lệnh:

```powershell
cd C:\Users\Admin\Desktop\W-12LAB\TF3-Self-Heal-Agent-AWS\infra\envs\dev
terraform destroy -auto-approve
aws eks list-clusters --region ap-southeast-1
```
