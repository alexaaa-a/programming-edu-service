kubeconfig_path = "~/.kube/config"
kube_context    = "minikube"

namespaces = [
  "platform",
  "gitops",
  "dev",
  "staging",
  "prod",
  "kafka",
]

service_accounts = [
  {
    name      = "ci-deployer"
    namespace = "gitops"
  },
  {
    name      = "app-runner"
    namespace = "dev"
  },
]

base_secrets = {
  "global-app-secrets" = {
    namespace = "dev"
    data = {
      REDIS_PASSWORD = "replace-me"
      JWT_SECRET     = "replace-me"
    }
  }
}
