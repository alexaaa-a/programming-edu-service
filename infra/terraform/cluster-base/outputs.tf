output "namespaces" {
  description = "Created namespaces."
  value       = keys(kubernetes_namespace.base)
}

output "service_accounts" {
  description = "Created service accounts."
  value = [
    for k, v in kubernetes_service_account.base :
    {
      key       = k
      name      = v.metadata[0].name
      namespace = v.metadata[0].namespace
    }
  ]
}

output "argocd_bootstrap_secret_name" {
  description = "Secret containing generated ArgoCD bootstrap admin password."
  value       = kubernetes_secret.argocd_bootstrap_admin_password.metadata[0].name
}

output "argocd_bootstrap_admin_password" {
  description = "Generated ArgoCD bootstrap admin password."
  value       = random_password.argocd_admin.result
  sensitive   = true
}
