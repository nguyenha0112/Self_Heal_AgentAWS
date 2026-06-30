# AI Source Sync Evidence

## Nguồn tham chiếu AI

- AI source repo: `https://github.com/AIops-g4/Capstone-Phase-2-Code.git`
- Branch đã kiểm tra: `main`
- Commit đã fetch và đối chiếu: `1a0c949`
- Ngày kiểm tra local: `2026-06-30`

## Kết luận đồng bộ

- Repo deploy hiện tại đã bám contract detect/decide/verify và boundary "AI chỉ decide, CDO mới execute".
- AI image thật vẫn chưa được team AI handoff trong repo deploy, nên phần wrapper deployment được giữ sẵn ở `manifests/ai-engine/deployment.yaml.template`.
- Executor đã được chỉnh sang mode `python main.py --watch` để khớp hệ thống runtime thay vì `sleep infinity` hoặc `run_scenarios.py`.
- Monitoring được mở rộng để sẵn sàng scrape `ai-engine` khi image thật được cung cấp.

## Mapping đã chốt

| Hạng mục | Nguồn AI | Repo deploy |
|---|---|---|
| API contract | `tf-3/ai/contracts/ai-api-contract.md` | executor client / docs / deploy wrapper |
| Deployment contract | `tf-3/ai/contracts/deployment-contract.md` | `manifests/ai-engine/deployment.yaml.template`, RBAC, network policy |
| AI unified server | `tf-3/ai/ai-engine/detect_decide/` | chờ image handoff, không copy logic AI vào repo deploy |
| Metrics endpoint | AI `/metrics` | `ServiceMonitor` cho `ai-engine` trong `manifests/monitoring/` |

## Chỗ còn chờ team AI

- `AI_ENGINE_IMAGE`
- nếu image AI đổi path health/readiness/metrics thì cập nhật lại wrapper manifest trước khi apply
