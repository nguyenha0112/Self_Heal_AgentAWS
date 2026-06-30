resource "aws_cloudwatch_log_group" "executor" {
  name              = "/cdo/${var.environment}/executor"
  retention_in_days = 7
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

resource "helm_release" "kube_prometheus_stack" {
  count            = var.enable_prometheus_stack ? 1 : 0
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true

  values = [yamlencode({
    grafana = {
      enabled                   = var.enable_grafana
      adminPassword             = "admin123!"
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
}
