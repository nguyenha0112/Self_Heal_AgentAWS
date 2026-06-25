resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  namespace        = "argocd"
  create_namespace = true
  version          = "7.7.15"

  # Server ClusterIP only — không expose public, access qua kubectl port-forward
  set {
    name  = "server.service.type"
    value = "ClusterIP"
  }

  # Tắt TLS cho server (dùng trong cluster, không cần cert)
  set {
    name  = "configs.params.server\\.insecure"
    value = "true"
  }
}
