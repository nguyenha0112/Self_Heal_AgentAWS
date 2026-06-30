
output "monitoring_namespace" {
  value = "monitoring"
}

output "prometheus_enabled" {
  value = var.enable_prometheus_stack
}

output "grafana_enabled" {
  value = var.enable_grafana
}

output "alertmanager_enabled" {
  value = var.enable_alertmanager
}

output "otel_collector_enabled" {
  value = var.enable_otel_collector
}
