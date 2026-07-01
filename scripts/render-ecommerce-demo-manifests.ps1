param(
  [string]$DemoRepo = "D:\Xbrain\Phase2\react-ecommerce",
  [string]$OutputDir = "D:\Xbrain\Phase2\nguyen\Self_Heal_AgentAWS\manifests\workloads",
  [Parameter(Mandatory = $true)]
  [string]$ApiImage,
  [Parameter(Mandatory = $true)]
  [string]$WebImage
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path -LiteralPath $DemoRepo
$out = New-Item -ItemType Directory -Force -Path $OutputDir

$files = @(
  "manifests\apps\ecommerce-api-tenant-a.yaml",
  "manifests\apps\ecommerce-api-tenant-b.yaml",
  "manifests\apps\ecommerce-web-tenant-a.yaml",
  "manifests\apps\ecommerce-web-tenant-b.yaml"
)

foreach ($rel in $files) {
  $src = Join-Path $repo $rel
  if (-not (Test-Path -LiteralPath $src)) {
    throw "Missing demo manifest: $src"
  }

  $text = Get-Content -Raw -LiteralPath $src
  $text = $text.Replace(
    "AWS_ACCOUNT_ID.dkr.ecr.AWS_REGION.amazonaws.com/tf3-cdo02/ecommerce-api:latest",
    $ApiImage
  )
  $text = $text.Replace(
    "AWS_ACCOUNT_ID.dkr.ecr.AWS_REGION.amazonaws.com/tf3-cdo02/ecommerce-web:latest",
    $WebImage
  )
  $text = $text.Replace("CHANGE_ME_ECOMMERCE_API_IMAGE", $ApiImage)
  $text = $text.Replace("CHANGE_ME_ECOMMERCE_WEB_IMAGE", $WebImage)

  $dst = Join-Path $out ([IO.Path]::GetFileName($rel))
  Set-Content -LiteralPath $dst -Value $text -Encoding utf8
  Write-Host "Rendered $dst"
}

Write-Host ""
Write-Host "Next:"
Write-Host "  kubectl apply -f manifests/workloads/ecommerce-api-tenant-a.yaml"
Write-Host "  kubectl apply -f manifests/workloads/ecommerce-api-tenant-b.yaml"
Write-Host "  kubectl apply -f manifests/workloads/ecommerce-web-tenant-a.yaml"
Write-Host "  kubectl apply -f manifests/workloads/ecommerce-web-tenant-b.yaml"
Write-Host "  kubectl apply -f manifests/observability/servicemonitor-ecommerce-demo.yaml"
