resource "aws_cloudwatch_log_group" "eks_cluster" {
  name              = "/aws/eks/${var.cluster_name}/cluster"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "executor" {
  name              = "/cdo/${var.environment}/executor"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "self_heal_audit" {
  name              = "/cdo/${var.environment}/audit"
  retention_in_days = 30
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
