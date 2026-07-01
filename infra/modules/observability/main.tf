resource "aws_cloudwatch_log_group" "executor" {
  name              = "/cdo/${var.environment}/executor"
  retention_in_days = 7
}

locals {
  monitoring_namespace = "monitoring"
  grafana_secret_name  = "grafana-admin-credentials"
  monitoring_enabled   = var.enable_prometheus_stack || var.enable_otel_collector
}

resource "aws_cloudwatch_log_group" "self_heal_audit" {
  name              = "/cdo/${var.environment}/audit"
  retention_in_days = 7
  # S3 Object Lock (GOVERNANCE, 90 ngay) la source of truth cho audit.
  # CloudWatch chi phuc vu query real-time, 7 ngay la du.
}

resource "aws_cloudwatch_log_group" "argocd" {
  name              = "/cdo/${var.environment}/argocd"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "kyverno" {
  name              = "/cdo/${var.environment}/kyverno"
  retention_in_days = 7
}

resource "kubernetes_namespace_v1" "monitoring" {
  count = local.monitoring_enabled ? 1 : 0

  metadata {
    name = local.monitoring_namespace
  }
}

resource "random_password" "grafana_admin" {
  count   = var.enable_prometheus_stack && var.enable_grafana ? 1 : 0
  length  = 24
  special = true
}

resource "kubernetes_secret_v1" "grafana_admin" {
  count = var.enable_prometheus_stack && var.enable_grafana ? 1 : 0

  metadata {
    name      = local.grafana_secret_name
    namespace = local.monitoring_namespace
  }

  type = "Opaque"

  data = {
    admin-user     = var.grafana_admin_username
    admin-credential = random_password.grafana_admin[0].result
  }

  depends_on = [kubernetes_namespace_v1.monitoring]
}

resource "helm_release" "kube_prometheus_stack" {
  count            = var.enable_prometheus_stack ? 1 : 0
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = local.monitoring_namespace
  create_namespace = false

  values = [yamlencode({
    grafana = {
      enabled = var.enable_grafana
      admin = {
        existingSecret = local.grafana_secret_name
        userKey        = "admin-user"
        passwordKey    = "admin-credential"
      }
      defaultDashboardsTimezone = "browser"
      sidecar = {
        dashboards = {
          enabled = true
          label   = "grafana_dashboard"
        }
        datasources = {
          enabled = true
        }
      }
    }
    alertmanager = {
      enabled = var.enable_alertmanager
    }
    prometheus = {
      prometheusSpec = {
        retention                               = "7d"
        serviceMonitorSelectorNilUsesHelmValues = false
        podMonitorSelectorNilUsesHelmValues     = false
        ruleSelectorNilUsesHelmValues           = false
      }
    }
    prometheusOperator = {
      enabled = true
    }
  })]

  depends_on = [kubernetes_secret_v1.grafana_admin]
}

resource "helm_release" "otel_collector" {
  count            = var.enable_otel_collector ? 1 : 0
  name             = "opentelemetry-collector"
  repository       = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart            = "opentelemetry-collector"
  namespace        = local.monitoring_namespace
  create_namespace = false

  values = [yamlencode({
    mode = "deployment"
    image = {
      repository = "otel/opentelemetry-collector-k8s"
      tag        = "0.102.1"
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
        telemetry = {
          metrics = {
            readers = [{
              pull = {
                exporter = {
                  prometheus = {
                    host = "$${env:MY_POD_IP}"
                    port = 8889
                  }
                }
              }
            }]
          }
          resource = {
            "host.name"          = "$${env:OTEL_K8S_NODE_NAME}"
            "k8s.namespace.name" = "$${env:OTEL_K8S_NAMESPACE}"
            "k8s.node.ip"        = "$${env:OTEL_K8S_NODE_IP}"
            "k8s.node.name"      = "$${env:OTEL_K8S_NODE_NAME}"
            "k8s.pod.ip"         = "$${env:OTEL_K8S_POD_IP}"
            "k8s.pod.name"       = "$${env:OTEL_K8S_POD_NAME}"
          }
        }
      }
    }
  })]

  depends_on = [kubernetes_namespace_v1.monitoring]
}
