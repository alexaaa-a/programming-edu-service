resource "kubernetes_namespace" "base" {
  for_each = toset(var.namespaces)

  metadata {
    name = each.value
    labels = {
      "managed-by" = "terraform"
    }
  }
}

resource "kubernetes_service_account" "base" {
  for_each = {
    for sa in var.service_accounts :
    "${sa.namespace}/${sa.name}" => sa
  }

  metadata {
    name      = each.value.name
    namespace = each.value.namespace
    labels = {
      "managed-by" = "terraform"
    }
  }

  depends_on = [kubernetes_namespace.base]
}

resource "random_password" "argocd_admin" {
  length           = 24
  special          = true
  override_special = "_%@"
}

locals {
  base_secrets_for_each = {
    for name in nonsensitive(keys(var.base_secrets)) :
    name => var.base_secrets[name]
  }
}

resource "kubernetes_secret" "base" {
  for_each = local.base_secrets_for_each

  metadata {
    name      = each.key
    namespace = each.value.namespace
    labels = {
      "managed-by" = "terraform"
    }
  }

  data = each.value.data
  type = "Opaque"

  depends_on = [kubernetes_namespace.base]
}

resource "kubernetes_secret" "argocd_bootstrap_admin_password" {
  metadata {
    name      = "argocd-bootstrap-admin"
    namespace = "gitops"
    labels = {
      "managed-by" = "terraform"
    }
  }

  data = {
    password = random_password.argocd_admin.result
  }
  type = "Opaque"

  depends_on = [kubernetes_namespace.base]
}
