"""
Deferred executor (Path A — GitOps) — CDO KHÔNG mutate K8s trực tiếp.
Flow: Git commit cập nhật manifest → ArgoCD sync → poll status Synced+Healthy → verify.
Rollback luôn đi qua revert commit → ArgoCD sync (04_deployment_design §3.5.1).

SKELETON: đây là path RỦI RO/TỐN THỜI GIAN nhất — cân nhắc hạ về designed-only nếu
urgent path chưa xong (xem đánh giá 5-ngày). Để stub có chủ đích.
"""
from __future__ import annotations

import sys
import time

from models import DecideResponse

from .base import ActionExecutor, ExecutionResult


class DeferredExecutor(ActionExecutor):
    def execute(self, decide: DecideResponse) -> ExecutionResult:
        item = decide.action_plan[0]
        # TODO(W12):
        # 1. clone/checkout manifest repo
        # 2. patch manifests/<tenant>/<svc>/values.yaml (replicas hoặc secret config)
        # 3. git commit + push (GitHub App token, KHÔNG dùng PAT tĩnh)
        # 4. poll ArgoCD Application: chờ Synced + Healthy trong verify_policy.window_seconds
        # 5. nếu timeout/SyncFailed → revert commit + escalate
        print(
            f"[deferred][STUB] {item.action} target={item.target} — GitOps CHƯA implement: "
            "KHÔNG có commit/sync thật. status=COMPLETED chỉ để chạy hết loop ở mock; "
            "với test LIVE action deferred này KHÔNG tác động cluster.",
            file=sys.stderr,
        )
        return ExecutionResult(
            action=item.action, target=item.target, status="COMPLETED",
            execution_time_seconds=0,
            detail={"path": "deferred_gitops", "stub": True, "applied": False,
                    "note": "DESIGNED-ONLY: implement Git→ArgoCD ở W12 (cần repo manifest + token push)"},
        )

    def rollback(self, decide: DecideResponse, snapshot) -> ExecutionResult:
        item = decide.action_plan[0]
        # TODO(W12): tạo revert commit về snapshot.git_sha → ArgoCD sync về cũ
        return ExecutionResult(item.action, item.target, "COMPLETED",
                               detail={"rollback": "revert_commit", "git_sha": getattr(snapshot, "git_sha", None)})

    @staticmethod
    def _wait_argocd_synced(app: str, timeout_s: int) -> bool:
        # TODO(W12): gọi ArgoCD API/kubectl chờ status
        deadline = time.time() + timeout_s
        return time.time() < deadline
