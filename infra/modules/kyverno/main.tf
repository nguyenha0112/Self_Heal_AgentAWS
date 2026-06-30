resource "helm_release" "kyverno" {
  name             = "kyverno"
  repository       = "https://kyverno.github.io/kyverno/"
  chart            = "kyverno"
  namespace        = "kyverno"
  create_namespace = true
  version          = "3.2.7"

  set {
    name  = "admissionController.replicas"
    value = "1"
  }

  set {
    name  = "backgroundController.replicas"
    value = "1"
  }

  set {
    name  = "cleanupController.replicas"
    value = "1"
  }

  set {
    name  = "reportsController.replicas"
    value = "1"
  }

  set {
    name  = "policyReportsCleanup.enabled"
    value = "false"
  }

  set {
    name  = "cleanupJobs.admissionReports.enabled"
    value = "false"
  }

  set {
    name  = "cleanupJobs.clusterAdmissionReports.enabled"
    value = "false"
  }

  set {
    name  = "cleanupJobs.ephemeralReports.enabled"
    value = "false"
  }

  set {
    name  = "cleanupJobs.clusterEphemeralReports.enabled"
    value = "false"
  }
}
