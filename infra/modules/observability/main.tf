resource "aws_cloudwatch_log_group" "executor" {
  name              = "/cdo/${var.environment}/executor"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "self_heal_audit" {
  name              = "/cdo/${var.environment}/audit"
  retention_in_days = 7
  # S3 Object Lock (GOVERNANCE, 90 ngày) là source of truth cho audit.
  # CloudWatch chỉ phục vụ query real-time — 7 ngày là đủ.
}

resource "aws_cloudwatch_log_group" "argocd" {
  name              = "/cdo/${var.environment}/argocd"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "kyverno" {
  name              = "/cdo/${var.environment}/kyverno"
  retention_in_days = 7
}

# Alarm: executor log errors
resource "aws_cloudwatch_metric_alarm" "executor_errors" {
  alarm_name          = "cdo-executor-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ErrorCount"
  namespace           = "CDO/Executor"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "CDO executor error rate > 5 trong 1 phút — check audit log"
  treat_missing_data  = "notBreaching"
}

# Alarm: Kyverno policy deny spike
resource "aws_cloudwatch_metric_alarm" "kyverno_deny_spike" {
  alarm_name          = "cdo-kyverno-deny-spike-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "PolicyDenyCount"
  namespace           = "CDO/Kyverno"
  period              = 300
  statistic           = "Sum"
  threshold           = 3
  alarm_description   = "Kyverno deny > 3 trong 5 phút — có thể là unsafe action attempt"
  treat_missing_data  = "notBreaching"
}

# Alarm: DLQ malformed telemetry rate > 0.5% trong 5 phút
# Requirement: telemetry contract-new-2 Section 2.5.B
resource "aws_cloudwatch_metric_alarm" "dlq_malformed_rate" {
  alarm_name          = "cdo-dlq-malformed-rate-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0.5
  alarm_description   = "DLQ malformed telemetry > 0.5% tổng lưu lượng trong 5 phút (telemetry contract-new-2 §2.5.B)"
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "malformed_rate"
    expression  = "IF(total_msgs > 0, dlq_msgs / total_msgs * 100, 0)"
    label       = "DLQ Malformed Rate (%)"
    return_data = true
  }

  metric_query {
    id = "dlq_msgs"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "NumberOfMessagesSent"
      dimensions  = { QueueName = var.dlq_queue_name }
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id = "total_msgs"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "NumberOfMessagesSent"
      dimensions  = { QueueName = var.sqs_queue_name }
      period      = 300
      stat        = "Sum"
    }
  }
}

resource "helm_release" "kube_prometheus_stack" {
  count            = var.enable_prometheus_stack ? 1 : 0
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true

  values = [yamlencode({
    grafana = {
      enabled = var.enable_grafana
    }
    alertmanager = {
      enabled = var.enable_alertmanager
    }
    prometheus = {
      prometheusSpec = {
        retention                               = "7d"
        serviceMonitorSelectorNilUsesHelmValues = false
      }
    }
  })]
}

resource "helm_release" "otel_collector" {
  count            = var.enable_otel_collector ? 1 : 0
  name             = "opentelemetry-collector"
  repository       = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart            = "opentelemetry-collector"
  namespace        = "monitoring"
  create_namespace = true

  values = [yamlencode({
    mode = "deployment"
    image = {
      repository = "ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-k8s"
    }
    command = {
      name = "otelcol-k8s"
    }
    config = {
      receivers = {
        otlp = {
          protocols = {
            grpc = {}
            http = {}
          }
        }
      }
      processors = {
        batch = {}
      }
      exporters = {
        debug = {
          verbosity = "normal"
        }
      }
      service = {
        pipelines = {
          traces = {
            receivers  = ["otlp"]
            processors = ["batch"]
            exporters  = ["debug"]
          }
          metrics = {
            receivers  = ["otlp"]
            processors = ["batch"]
            exporters  = ["debug"]
          }
          logs = {
            receivers  = ["otlp"]
            processors = ["batch"]
            exporters  = ["debug"]
          }
        }
      }
    }
  })]
}
