variable "cluster_name" {}
variable "environment" { default = "dev" }
variable "sqs_queue_name" {}
variable "dlq_queue_name" {}

variable "enable_prometheus_stack" {
  type    = bool
  default = true
}

variable "enable_grafana" {
  type    = bool
  default = true
}

variable "enable_alertmanager" {
  type    = bool
  default = false
}

variable "enable_otel_collector" {
  type    = bool
  default = true
}
