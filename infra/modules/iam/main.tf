# IRSA — CDO Self-Heal Executor
# Cho phép executor pod gọi S3 (audit write), DynamoDB (idempotency), SQS, CloudWatch

locals {
  oidc_subject = "${replace(var.oidc_issuer_url, "https://", "")}:sub"
}

data "aws_iam_policy_document" "executor_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = local.oidc_subject
      values   = ["system:serviceaccount:platform:cdo-executor"]
    }
  }
}

resource "aws_iam_role" "executor" {
  name               = "cdo-executor-irsa-${var.cluster_name}"
  assume_role_policy = data.aws_iam_policy_document.executor_trust.json
}

data "aws_iam_policy_document" "executor_policy" {
  statement {
    sid    = "AuditS3Write"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.audit_bucket_name}",
      "arn:aws:s3:::${var.audit_bucket_name}/*",
    ]
  }

  statement {
    sid    = "IdempotencyDynamo"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [var.dynamodb_table_arn]
  }

  statement {
    sid    = "TelemetrySQS"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid    = "CloudWatchMetricsAndLogs"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
      "cloudwatch:GetMetricStatistics",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "executor" {
  name   = "cdo-executor-policy"
  role   = aws_iam_role.executor.id
  policy = data.aws_iam_policy_document.executor_policy.json
}
