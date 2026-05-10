variable "kubeconfig_path" {
  description = "Absolute path to kubeconfig file."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubeconfig context name."
  type        = string
  default     = "minikube"
}

variable "namespaces" {
  description = "List of base namespaces to create."
  type        = list(string)
  default = [
    "platform",
    "gitops",
    "dev",
    "staging",
    "prod",
    "kafka",
  ]
}

variable "service_accounts" {
  description = "Service accounts to create in namespaces."
  type = list(object({
    name      = string
    namespace = string
  }))
  default = [
    {
      name      = "ci-deployer"
      namespace = "gitops"
    },
    {
      name      = "app-runner"
      namespace = "dev"
    },
  ]
}

variable "base_secrets" {
  description = "Map of secret name => namespace and stringData values."
  type = map(object({
    namespace = string
    data      = map(string)
  }))
  default = {
    "global-app-secrets" = {
      namespace = "dev"
      data = {
        REDIS_PASSWORD = "change-me"
        JWT_SECRET     = "change-me-too"
      }
    }
  }
  sensitive = true
}
