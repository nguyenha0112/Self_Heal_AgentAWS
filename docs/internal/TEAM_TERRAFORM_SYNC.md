# Team Terraform Sync

Muc tieu: tat ca thanh vien cung dung chung remote Terraform state tren S3 de `plan/apply` khong bi lech.

## Shared Backend

- Branch: `chore/argocd-team-setup`
- AWS region: `ap-southeast-1`
- S3 bucket: `cdo-tf-state-012619468490-ap-southeast-1-dev`
- State key: `envs/dev/terraform.tfstate`

## Cac buoc cho thanh vien moi

```bash
git fetch origin
git checkout chore/argocd-team-setup
aws configure
aws sts get-caller-identity
cd infra/envs/dev
terraform init
terraform state pull
terraform plan
```

## Kiem tra da noi dung state chung

```bash
terraform state pull
aws s3 ls s3://cdo-tf-state-012619468490-ap-southeast-1-dev/envs/dev/ --region ap-southeast-1
```

Neu thay object `terraform.tfstate` va `terraform state pull` tra JSON thi da noi dung backend chung.

## Quy tac lam viec nhom

- Chi 1 nguoi chay `terraform apply` tai 1 thoi diem.
- Nguoi khac duoc phep `terraform init`, `terraform state pull`, `terraform plan`.
- Neu gap state lock, dung tu y force unlock neu chua xac nhan nguoi apply truoc da dung han.
- Khong commit file `.terraform/`, `terraform.tfstate`, `tfplan*.out`, secret, hay kubeconfig.

## ArgoCD

ArgoCD hien dang de `ClusterIP`, nen chua co public URL co dinh.

Tam thoi truy cap bang port-forward:

```bash
aws eks update-kubeconfig --name cdo-eks-cluster-dev --region ap-southeast-1
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Mo:

```text
https://localhost:8080
```

Lay mat khau admin:

```bash
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d && echo
```
