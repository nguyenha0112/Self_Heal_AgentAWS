# CDO-02 AI Handoff Requirements

Thu muc nay mirror goi `requirements/` dung de ban giao du lieu runtime cho ben AI
nhung nam ben trong repo de co the review, test va day len GitHub.

## File chinh

- `platform_profile_CDO02.json`
  - Profile tong hop de review contract va schema.
  - Khong nen dung truc tiep cho production rule-based multi-tenant vi AI engine hien tai
    khong render dong duoc `namespace` va `deployment` theo tung service alias trong 1 profile duy nhat.
- `platform_profile_CDO02_tenant_a.json`
  - Profile production-safe cho workload `checkout-svc` o `tenant-a`.
- `platform_profile_CDO02_tenant_b.json`
  - Profile production-safe cho workload `notification-svc` o `tenant-b`.
- `service_registry_CDO02.json`
  - Bang mapping canonical giua `service`, `namespace`, `deployment`, `container`,
    service aliases va cac payload handoff/thuc nghiem da xuat hien.

## Canonical runtime mapping

- `checkout-svc` -> `tenant-a` -> `deployment/cdo-sample-api` -> `container/podinfo`
- `notification-svc` -> `tenant-b` -> `deployment/notification-service` -> `container/podinfo`

## Alias/stale data can luu y

- `orders-svc` va `cdo-orders-api` xuat hien trong mot so scenario cu; can duoc map ve
  `notification-svc` / `notification-service`.
- `notification-service` co luc duoc dung nhu deployment name, co luc duoc dung nhu service name.
  Gia tri canonical phia AI nen dung la `notification-svc` cho truong `service` va
  `notification-service` cho truong `deployment`.
