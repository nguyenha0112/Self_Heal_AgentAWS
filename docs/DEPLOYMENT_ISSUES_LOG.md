# Deployment Issues Log

Tai lieu nay tong hop cac loi da phat sinh trong qua trinh trien khai ha tang va cach da xu ly.

## 1. Sai account AWS so voi cau hinh repo ban dau

### Hien tuong

- AWS credentials hien tai tra ve account `012619468490`.
- Repo ban dau dang tro toi:
  - EKS cluster cu trong account khac
  - S3 backend bucket cu trong account khac

### Dau hieu nhan biet

- `aws sts get-caller-identity` tra ve account khong khop account cu trong doc/repo.
- `aws eks describe-cluster --name cdo-eks-cluster-dev` bao khong tim thay cluster.
- `aws s3 ls s3://...` bao bucket khong ton tai.

### Cach xu ly

- Doi cau hinh backend va bootstrap de phu hop account hien tai.
- Chuyen huong triem khai sang account AWS dang duoc cap credentials.

### Ket qua

- Co the bootstrap backend moi va dung chung state tren account hien tai.

## 2. Terraform backend S3 ban dau tro sai bucket/region

### Hien tuong

- `infra/envs/dev/providers.tf` ban dau van tro toi bucket cu.
- Sau khi doi region, Terraform van co luc co gang doc bucket o region cu.

### Nguyen nhan

- Backend `s3` trong `providers.tf` con gia tri bucket/region cu.
- Cache backend local trong `.terraform/` con luu cau hinh cu.

### Cach xu ly

- Cap nhat lai:
  - ten bucket backend
  - region backend
- Xoa cache `.terraform/` cua thu muc `infra/envs/dev`.
- Chay lai `terraform init -reconfigure`.

### Ket qua

- Backend da duoc noi sang bucket S3 moi tai Singapore:
  - `cdo-tf-state-012619468490-ap-southeast-1-dev`

## 3. Bootstrap tfstate bucket o sai region

### Hien tuong

- Luc dau bucket tfstate duoc tao o `us-east-1`.
- Yeu cau sau do la chuyen sang `ap-southeast-1`.

### Nguyen nhan

- Repo va bootstrap ban dau hardcode `us-east-1`.

### Cach xu ly

- Sua `infra/bootstrap/main.tf` de dung region `ap-southeast-1`.
- Sinh ten bucket theo account + region de tranh nham lan.
- Tao lai bucket moi o Singapore.

### Ket qua

- Bucket dung cho teamwork da ton tai o:
  - `ap-southeast-1`
  - `cdo-tf-state-012619468490-ap-southeast-1-dev`

## 4. Nhieu file/tai lieu hardcode `us-east-1`

### Hien tuong

- Region cu xuat hien trong:
  - Terraform variables/backend
  - VPC endpoint service names
  - IAM ARN cho Bedrock va Secrets Manager
  - Executor manifest
  - AI deployment template
  - Build guide

### Cach xu ly

- Rà soat va chuyen cac diem hardcode chinh sang `ap-southeast-1`.
- Bo sung bien `aws_region` vao module can thiet.
- Cap nhat huong dan cho team va build guide.

### Ket qua

- Cau hinh teamwork va build guide da dong bo theo Singapore.

## 5. Terraform validate fail vi module chua init

### Hien tuong

- `terraform validate` bao `Module not installed`.

### Nguyen nhan

- Chua chay `terraform init` hoac dang chay validate song song khi init chua xong.

### Cach xu ly

- Chay `terraform init -backend=false` hoac `terraform init`.
- Chay lai `terraform validate` theo thu tu, khong chay song song voi init.

### Ket qua

- Cau hinh Terraform sau khi sua da validate thanh cong.

## 6. Loi PowerShell khi dung `terraform plan -out=...`

### Hien tuong

- Terraform bao `Too many command line arguments`.

### Nguyen nhan

- PowerShell parse tham so `-out=...` theo cach gay loi trong mot so lan goi lenh.

### Cach xu ly

- Dung cu phap an toan hon:

```bash
terraform plan "-out=tfplan-singapore.out"
```

### Ket qua

- Plan duoc tao thanh cong.

## 7. State lock bi keo dai sau khi apply bi ngat

### Hien tuong

- `terraform apply` hoac `destroy` bao:
  - `Error acquiring the state lock`

### Nguyen nhan

- Cac lenh apply truoc do bi ngat giua chung.
- Lockfile tren S3 con ton tai hoac o trang thai khong dong bo.

### Cach xu ly

- Dung `terraform force-unlock -force <LOCK_ID>` de go lock cua chinh session da bi ngat.
- Sau do chay lai lenh tiep theo.

### Ket qua

- Co the tiep tuc thao tac voi remote state.

## 8. Lockfile S3 o trang thai loi sau nhieu lan ngat lenh

### Hien tuong

- Sau khi unlock, van co lan Terraform bao:
  - precondition failed
  - hoac khong tim thay `.tflock`

### Nguyen nhan

- Lockfile native cua S3 bi lech trang thai do nhieu lan apply bi interrupt.

### Cach xu ly

- Xac dinh day la backend chi co minh dang thao tac.
- Thu force-unlock truoc.
- Neu lock tiep tuc loi do session cu, chuyen sang uu tien xu ly cau hinh/teamwork state truoc thay vi tiep tuc apply dai.

### Ket qua

- Backend teamwork tren S3 van duoc thiet lap xong.
- Full apply van chua duoc chot hoan toan trong turn do bi interrupt nhieu lan.

## 9. Cache `.terraform/` bi hong sau khi xoa/chuyen backend

### Hien tuong

- Terraform bao:
  - `Unreadable module directory`
  - khong tim thay `.terraform/modules/...`

### Nguyen nhan

- Thu muc `.terraform/` o local dang o trang thai nua cu nua moi sau khi doi backend/region.

### Cach xu ly

- Xoa cache `.terraform/` o thu muc bi anh huong.
- Chay:

```bash
terraform get -update
terraform init -reconfigure
```

### Ket qua

- Module duoc tai lai va backend duoc noi lai thanh cong.

## 10. Provider AWS bi khoa boi process cu tren Windows

### Hien tuong

- Terraform bao khong mo duoc file provider AWS vi file dang duoc process khac su dung.

### Nguyen nhan

- Session Terraform truoc do chua giai phong file provider tren Windows.

### Cach xu ly

- Chay lai theo thu tu, khong song song.
- Tranh vua init vua validate/apply cung luc.
- Sau khi process cu ket thuc, chay lai `terraform init -reconfigure`.

### Ket qua

- Provider duoc tai va su dung lai binh thuong.

## 11. `kubectl` bi timeout du cluster da ACTIVE

### Hien tuong

- `kubectl get ns`, `kubectl get svc -n argocd`, `kubectl cluster-info` bi treo/timeout.

### Nguyen nhan

- EKS cluster dang de:
  - `endpointPublicAccess: false`
  - `endpointPrivateAccess: true`
- Nghia la Kubernetes API chi truy cap duoc tu ben trong VPC.

### Cach xu ly

- Kiem tra qua AWS API thay vi chi dua vao `kubectl`.
- Xac nhan cluster van `ACTIVE`.
- Ket luan chinh xac rang cluster dang private-only, nen tu ngoai VPC khong the vao kubectl de verify/expose ArgoCD.

### Ket qua

- Xac dinh duoc ly do chua the lay link ArgoCD.
- Day la van de thiet ke truy cap, khong phai cluster bi down.

## 12. Khong the lay link ArgoCD cho team

### Hien tuong

- Chua co public URL de gui cho team.

### Nguyen nhan

- ArgoCD trong thiet ke dang la `ClusterIP`.
- Cluster EKS hien private-only.
- Tu ngoai VPC khong the dung `kubectl` de kiem tra va expose service nhanh.

### Cach xu ly da lam

- Kiem tra thuc trang cluster qua AWS API.
- Xac nhan ro nguyen nhan la do private endpoint va ArgoCD khong public.

### Trang thai hien tai

- Chua co link ArgoCD share ca nhom.
- Neu muon co link thi can mot trong cac cach:
  - mo public EKS API co kiem soat
  - dung may/bastion nam trong VPC
  - expose ArgoCD bang internal/public LoadBalancer sau khi co duong quan tri vao cluster

## 13. File plan/local artifact khong nen push

### Hien tuong

- Trong qua trinh deploy, xuat hien cac file local nhu:
  - `tfplan*.out`
  - `.terraform/`
  - `terraform.tfstate`
  - ghi chu ca nhan

### Cach xu ly

- Them ignore cho `tfplan*.out`.
- Giu file ca nhan o local-only.
- Khong add/push cac artifact private va local state.

### Ket qua

- Nhanh nao duoc push chi gom code/tai lieu cong khai can thiet.

## 14. Ket qua tong hop sau cac xu ly

### Da xong

- Push code len nhanh `chore/argocd-team-setup`
- Tao shared backend S3 o Singapore
- Noi `infra/envs/dev` vao shared backend
- Tao object state dung chung tren S3
- EKS cluster o `ap-southeast-1` da len `ACTIVE`
- Bo sung huong dan teamwork sync Terraform state

### Chua chot xong

- Full `terraform apply` cho toan bo stack chua duoc ket thuc sach do nhieu lan session bi interrupt
- ArgoCD chua co link de share cho ca nhom
- Cluster dang private-only nen khong the verify/expose ArgoCD tu may ngoai VPC

## 15. Bai hoc rut ra

- Can chot account + region truoc khi bootstrap state bucket.
- Khong nen apply EKS/Helm dang khi session de bi interrupt nhieu lan.
- Khi doi backend hoac region, can lam sach `.terraform/` local.
- EKS private endpoint an toan hon, nhung se lam cham viec verify/van hanh neu khong co bastion/VPN/public access co kiem soat.
