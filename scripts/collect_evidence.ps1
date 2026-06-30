param(
    [string]$TenantId = "6c8b4b2b-4d45-4209-a1b4-4b532d56a31c",
    [string]$AuditBucket = "",
    [string]$OutputDir = ".\evidence\w12-monitoring\runtime-capture"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

kubectl get pods -A | Out-File -FilePath (Join-Path $OutputDir "pods-all.txt") -Encoding utf8
kubectl get servicemonitor -n monitoring | Out-File -FilePath (Join-Path $OutputDir "servicemonitors.txt") -Encoding utf8
kubectl get prometheusrule -n monitoring | Out-File -FilePath (Join-Path $OutputDir "prometheusrules.txt") -Encoding utf8
kubectl get configmap grafana-dashboard-self-heal -n monitoring -o yaml | Out-File -FilePath (Join-Path $OutputDir "grafana-dashboard.yaml") -Encoding utf8
kubectl logs deploy/cdo-executor -n self-heal-system --tail=200 | Out-File -FilePath (Join-Path $OutputDir "executor-tail.log") -Encoding utf8

if ($AuditBucket -ne "") {
    aws s3 ls "s3://$AuditBucket/audit/$TenantId/" | Out-File -FilePath (Join-Path $OutputDir "audit-objects.txt") -Encoding utf8
}

Write-Host "Evidence collected into $OutputDir"
