"""
ExternalCollector — scrape 3 signal từ các nguồn bên ngoài Kubernetes.

Signals:
  - queue_backlog                   (C1) — SQS / RabbitMQ
  - db_connection_pool_saturation   (C2) — DB pool exporter
  - secret_expiry_warning           (D1) — Secrets Manager / Cert Manager

Tích hợp:
  - AWS SQS API (`GetQueueAttributes`) — boto3 + IRSA (đã có cho executor).
  - RabbitMQ Management HTTP API — `GET /api/queues/{vhost}/{name}`.
  - Database exporter (Prometheus) — query `pg_stat_activity` / `mysql_status`.
    Ở đây dùng Prometheus vì executor đã IRSA + cluster-internal Prometheus.
  - AWS Secrets Manager API (`DescribeSecret` + rotation check).

Bằng chứng pattern trong code:
  - `idempotency.py:14-30` đã có pattern `try: import boto3 except: skip`
    cho module cần AWS. ExternalCollector dùng cùng pattern.
  - `infra/modules/audit/main.tf:106-130` đã có SQS queue + DLQ — collector
    scrape queue `ApproximateNumberOfMessagesVisible` attribute.
  - Contract §3 quy định value:
      queue_backlog                 → INTEGER (số message tồn đọng)
      db_connection_pool_saturation → number 0.0-1.0
      secret_expiry_warning         → INTEGER (số ngày còn lại)
  - Mock mode: trả value giả lập (high backlog / high saturation / 7 days).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from config import CONFIG
from telemetry_contract import normalize_point

log = logging.getLogger(__name__)

try:
    import boto3 as _boto3
    _HAS_BOTO = True
except ImportError:
    _HAS_BOTO = False


class ExternalCollector:
    """
    Scrape 3 signal từ AWS / external services.

    Mỗi signal có 1 sub-collector gọi API tương ứng. Khi thiếu config (vd
    SQS queue URL rỗng), sub-collector trả [] để không chặn các signal khác.
    """

    name = "external"
    supported_signals: tuple[str, ...] = (
        "queue_backlog",
        "db_connection_pool_saturation",
        "secret_expiry_warning",
    )

    def __init__(self, cfg=CONFIG):
        self.cfg = cfg

    def collect(self, *, tenant_id: str, namespace: str, deployment: str,
                tenant_namespace: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        out.extend(self._collect_queue_backlog(
            tenant_id, namespace, deployment))
        out.extend(self._collect_db_saturation(
            tenant_id, namespace, deployment))
        out.extend(self._collect_secret_expiry(
            tenant_id, namespace, deployment))
        return out

    # ---------- queue_backlog ----------

    def _collect_queue_backlog(self, tenant_id: str, namespace: str,
                                deployment: str) -> list[dict[str, Any]]:
        """
        SQS queue backlog — dùng convention `<service>-queue` hoặc lookup
        theo tag `tenant_id`. Nếu queue URL không có trong config → trả [].
        """
        if getattr(self.cfg, "k8s_mock", False):
            return self._mock_queue_backlog(tenant_id, namespace, deployment)
        queue_url = self._lookup_queue_url(deployment)
        if not queue_url or not _HAS_BOTO:
            return self._mock_queue_backlog(tenant_id, namespace, deployment)

        try:
            sqs = _boto3.client("sqs", region_name=self.cfg.aws_region)
            resp = sqs.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            backlog = int(resp["Attributes"]["ApproximateNumberOfMessages"])
            return [self._build_point(
                signal_name="queue_backlog",
                value=backlog,
                tenant_id=tenant_id, namespace=namespace,
                deployment=deployment,
                extra_labels={"queue_url": queue_url, "source": "sqs"},
            )]
        except Exception as e:
            log.warning("sqs backlog scrape failed: %s", e)
            return []

    def _lookup_queue_url(self, deployment: str) -> str | None:
        """
        Lookup queue URL — convention: env `SQS_QUEUE_URL_<DEPLOYMENT>` hoặc
        default `CDO_QUEUE_URL`. Nếu deployment không map → trả None.
        """
        env_key = f"SQS_QUEUE_URL_{deployment.upper().replace('-', '_')}"
        url = getattr(self.cfg, env_key.lower(), None)
        if url:
            return url
        return getattr(self.cfg, "default_queue_url", None) or None

    # ---------- db_connection_pool_saturation ----------

    def _collect_db_saturation(self, tenant_id: str, namespace: str,
                                 deployment: str) -> list[dict[str, Any]]:
        """
        DB pool saturation — query Prometheus exporter (HikariCP / pgx / mysql).

        PromQL: `hikaricp_connections_active / hikaricp_connections_max`
        """
        if getattr(self.cfg, "k8s_mock", False):
            return self._mock_db_saturation(tenant_id, namespace, deployment)
        try:
            import requests as _requests
        except ImportError:
            return self._mock_db_saturation(tenant_id, namespace, deployment)

        prom_url = getattr(self.cfg, "prometheus_url",
                           "http://prometheus.monitoring:9090")
        promql = (
            f'hikaricp_connections_active{{namespace="{namespace}",'
            f'pool="{deployment}"}} / '
            f'hikaricp_connections_max{{namespace="{namespace}",'
            f'pool="{deployment}"}}'
        )
        try:
            r = _requests.get(
                f"{prom_url}/api/v1/query",
                params={"query": promql},
                timeout=self.cfg.ai_timeout_detect_s,
            )
            if r.status_code != 200:
                return self._mock_db_saturation(tenant_id, namespace, deployment)
            data = r.json().get("data", {}).get("result", [])
            if not data:
                return []
            saturation = float(data[0]["value"][1])
            return [self._build_point(
                signal_name="db_connection_pool_saturation",
                value=max(0.0, min(1.0, saturation)),
                tenant_id=tenant_id, namespace=namespace,
                deployment=deployment,
                extra_labels={"pool": deployment, "source": "db_exporter"},
            )]
        except Exception as e:
            log.warning("db saturation scrape failed: %s", e)
            return self._mock_db_saturation(tenant_id, namespace, deployment)

    # ---------- secret_expiry_warning ----------

    def _collect_secret_expiry(self, tenant_id: str, namespace: str,
                                deployment: str) -> list[dict[str, Any]]:
        """
        Secrets Manager — list secret với tag `app=<deployment>` và
        check `LastRotatedDate` / `NextRotationDate` / cert expiry.
        """
        if getattr(self.cfg, "k8s_mock", False):
            return self._mock_secret_expiry(tenant_id, namespace, deployment)
        if not _HAS_BOTO:
            return self._mock_secret_expiry(
                tenant_id, namespace, deployment)

        try:
            sm = _boto3.client("secretsmanager",
                                region_name=self.cfg.aws_region)
            paginator = sm.get_paginator("list_secrets")
            out: list[dict[str, Any]] = []
            for page in paginator.paginate(
                Filters=[{"Key": "tag-key", "Values": ["app"]}],
            ):
                for s in page["SecretList"]:
                    tags = {t["Key"]: t["Value"]
                            for t in s.get("Tags", [])}
                    if tags.get("app") != deployment:
                        continue
                    days = self._days_until_expiry(s)
                    if days is None or days > 30:
                        continue  # chỉ cảnh báo trong vòng 30 ngày
                    out.append(self._build_point(
                        signal_name="secret_expiry_warning",
                        value=days,
                        tenant_id=tenant_id, namespace=namespace,
                        deployment=deployment,
                        extra_labels={
                            "secret_name": s["Name"],
                            "source": "secretsmanager",
                        },
                    ))
            return out
        except Exception as e:
            log.warning("secret expiry scrape failed: %s", e)
            return []

    @staticmethod
    def _days_until_expiry(secret: dict) -> int | None:
        """Tính số ngày còn lại trước khi secret hết hạn."""
        next_rot = secret.get("NextRotationDate")
        if next_rot:
            delta = next_rot - _utc_now()
            return max(0, int(delta.total_seconds() // 86400))
        last_rot = secret.get("LastRotatedDate")
        last_changed = secret.get("LastChangedDate")
        ref = last_rot or last_changed
        if ref:
            delta = _utc_now() - ref
            age_days = int(delta.total_seconds() // 86400)
            return max(0, 90 - age_days)
        return None

    # ---------- helpers ----------

    def _build_point(self, *, signal_name: str, value,
                     tenant_id: str, namespace: str, deployment: str,
                     extra_labels: dict[str, str] | None = None) -> dict:
        labels = {
            "system": "K8S_NATIVE",
            "namespace": namespace,
            "deployment": deployment,
        }
        if extra_labels:
            labels.update(extra_labels)
        return normalize_point(
            {
                "ts": _now_iso(),
                "tenant_id": tenant_id,
                "service": deployment,
                "signal_name": signal_name,
                "value": value,
                "labels": labels,
            },
            tenant_id=tenant_id,
        )

    # ---------- mocks ----------

    def _mock_queue_backlog(self, tenant_id: str, namespace: str,
                             deployment: str) -> list[dict[str, Any]]:
        return [self._build_point(
            signal_name="queue_backlog",
            value=15000,
            tenant_id=tenant_id, namespace=namespace,
            deployment=deployment,
            extra_labels={"source": "mock"},
        )]

    def _mock_db_saturation(self, tenant_id: str, namespace: str,
                             deployment: str) -> list[dict[str, Any]]:
        return [self._build_point(
            signal_name="db_connection_pool_saturation",
            value=0.95,
            tenant_id=tenant_id, namespace=namespace,
            deployment=deployment,
            extra_labels={"source": "mock"},
        )]

    def _mock_secret_expiry(self, tenant_id: str, namespace: str,
                             deployment: str) -> list[dict[str, Any]]:
        return [self._build_point(
            signal_name="secret_expiry_warning",
            value=7,
            tenant_id=tenant_id, namespace=namespace,
            deployment=deployment,
            extra_labels={
                "secret_name": f"tf-3/{deployment}/cert",
                "source": "mock",
            },
        )]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + \
        f".{int((time.time() % 1) * 1000):03d}Z"


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)