output "release_name" {
  description = "Helm release name of ArgoCD"
  value       = helm_release.argocd.name
}

output "namespace" {
  description = "Namespace where ArgoCD is installed"
  value       = helm_release.argocd.namespace
}

output "chart_version" {
  description = "Installed ArgoCD chart version"
  value       = helm_release.argocd.version
}
